#include "libpakdecrypt.h"
#include "ZipUtil.h"
#include "errors.h"
#include <tomcrypt.h>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <vector>

using namespace ZipUtil;

namespace {
int g_stage = 0;
struct Cursor {
  const std::vector<uint8_t> &data; size_t pos = 0;
  uint16_t u16() { if (pos + 2 > data.size()) throw std::runtime_error("truncated"); uint16_t v = uint16_t(data[pos]) | (uint16_t(data[pos + 1]) << 8); pos += 2; return v; }
  uint32_t u32() { if (pos + 4 > data.size()) throw std::runtime_error("truncated"); uint32_t v = uint32_t(data[pos]) | (uint32_t(data[pos + 1]) << 8) | (uint32_t(data[pos + 2]) << 16) | (uint32_t(data[pos + 3]) << 24); pos += 4; return v; }
  std::vector<uint8_t> take(size_t n) { if (pos + n > data.size()) throw std::runtime_error("truncated"); std::vector<uint8_t> v(data.begin() + pos, data.begin() + pos + n); pos += n; return v; }
};

struct ZipItem { CDRecord central{}; LocalFileHeader local{}; std::vector<uint8_t> centralDynamic, localDynamic, compressed; };

uint16_t read16(const std::vector<uint8_t> &b, size_t p) { if (p + 2 > b.size()) throw std::runtime_error("truncated"); return uint16_t(b[p]) | (uint16_t(b[p + 1]) << 8); }
uint32_t read32(const std::vector<uint8_t> &b, size_t p) { if (p + 4 > b.size()) throw std::runtime_error("truncated"); return uint32_t(b[p]) | (uint32_t(b[p + 1]) << 8) | (uint32_t(b[p + 2]) << 16) | (uint32_t(b[p + 3]) << 24); }
void appendBytes(std::vector<uint8_t> &out, const void *p, size_t n) { const uint8_t *b = static_cast<const uint8_t *>(p); out.insert(out.end(), b, b + n); }

size_t findEocd(const std::vector<uint8_t> &b) { for (size_t p = b.size(); p-- > 0;) { if (p + 22 <= b.size() && read32(b, p) == 0x06054b50u && p + 22 + read16(b, p + 20) == b.size()) return p; } throw std::runtime_error("CDR end record not found"); }
std::vector<uint8_t> readFile(const char *p) { std::ifstream in(p, std::ios::binary); if (!in) throw std::runtime_error("file not found"); return std::vector<uint8_t>((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>()); }

std::vector<uint8_t> crypt(TomCryption &crypto, const std::vector<uint8_t> &plain, CipherKey key, InitialVector iv) { std::vector<uint8_t> out = plain; if (!out.empty()) crypto.decryptData(out.data(), static_cast<unsigned long>(out.size()), key, iv); return out; }

CryEngineDecryptionKeys readKeys(const std::vector<uint8_t> &comment, TomCryption &crypto) {
  const size_t need = sizeof(CryEngineExtendedHeader) + sizeof(CryEngineSigningHeader) + sizeof(CryEngineEncryptionHeader); if (comment.size() < need) throw std::runtime_error("short encryption comment");
  CryEngineExtendedHeader ext{}; memcpy(&ext, comment.data(), sizeof(ext)); if (ext.headerSize != sizeof(ext) || ext.encryptionType != EncryptionType::StreamCipherKeytable) throw std::runtime_error("unsupported encryption");
  CryEngineEncryptionHeader enc{}; memcpy(&enc, comment.data() + sizeof(CryEngineExtendedHeader) + sizeof(CryEngineSigningHeader), sizeof(enc)); if (enc.headerSize != sizeof(enc)) throw std::runtime_error("bad encryption header");
  CryEngineDecryptionKeys result; for (int i = 0; i < BLOCK_CIPHER_NUM_KEYS; ++i) { auto p = crypto.decryptKey(enc.keys[i], RSA_KEY_MESSAGE_LENGTH, LTC_PKCS_1_OAEP); if (p.size() < BLOCK_CIPHER_KEY_LENGTH) throw std::runtime_error("bad key"); memcpy(result.cipherKeyTable[i], p.data(), BLOCK_CIPHER_KEY_LENGTH); } auto iv = crypto.decryptKey(enc.initVector, RSA_KEY_MESSAGE_LENGTH, LTC_PKCS_1_OAEP); if (iv.size() < BLOCK_CIPHER_KEY_LENGTH) throw std::runtime_error("bad iv"); memcpy(result.cdrInitialVector, iv.data(), BLOCK_CIPHER_KEY_LENGTH); return result;
}

std::vector<ZipItem> parseZip(const std::vector<uint8_t> &zip) {
  const size_t e = findEocd(zip); const uint16_t count = read16(zip, e + 10); Cursor c{zip, read32(zip, e + 16)}; std::vector<ZipItem> out; out.reserve(count);
  for (uint16_t i = 0; i < count; ++i) { ZipItem x; if (c.u32() != 0x02014b50u) throw std::runtime_error("bad central signature"); x.central.signature=0x02014b50u; x.central.versionAuthor=c.u16(); x.central.versionRequired=c.u16(); x.central.flags=c.u16(); x.central.method=c.u16(); x.central.modifiedTime=c.u16(); x.central.modifiedDate=c.u16(); x.central.descriptor.crc=c.u32(); x.central.descriptor.sizeCompressed=c.u32(); x.central.descriptor.sizeUncompressed=c.u32(); x.central.nameLength=c.u16(); x.central.extraFieldLength=c.u16(); x.central.commentLength=c.u16(); x.central.diskNumStart=c.u16(); x.central.attributeInternal=c.u16(); x.central.attributeExternal=c.u32(); x.central.localHeaderOffset=c.u32(); x.centralDynamic=c.take(x.central.nameLength+x.central.extraFieldLength+x.central.commentLength);
    Cursor l{zip,x.central.localHeaderOffset}; if(l.u32()!=0x04034b50u) throw std::runtime_error("bad local signature"); x.local.signature=0x04034b50u; x.local.versionRequired=l.u16(); x.local.flags=l.u16(); x.local.method=l.u16(); x.local.modifiedTime=l.u16(); x.local.modifiedDate=l.u16(); x.local.descriptor.crc=l.u32(); x.local.descriptor.sizeCompressed=l.u32(); x.local.descriptor.sizeUncompressed=l.u32(); x.local.nameLength=l.u16(); x.local.extraFieldLength=l.u16(); x.localDynamic=l.take(x.local.nameLength+x.local.extraFieldLength); x.compressed=l.take(x.central.descriptor.sizeCompressed); out.push_back(std::move(x)); }
  return out;
}

uint16_t encMethod(uint16_t m) { if(m==0) return static_cast<uint16_t>(CompressionMethod::StoreAndStreamcipherKeytable); if(m==8) return static_cast<uint16_t>(CompressionMethod::DeflateandStreamcipherKeytable); throw std::runtime_error("unsupported compression"); }

std::vector<uint8_t> serializeLocal(const ZipItem &x,uint16_t method) { std::vector<uint8_t> o; LocalFileHeader h=x.local; h.flags &= ~uint16_t(0x08); h.method=method; h.descriptor=x.central.descriptor; appendBytes(o,&h,sizeof(h)); appendBytes(o,x.localDynamic.data(),x.localDynamic.size()); return o; }
std::vector<uint8_t> serializeCentral(const ZipItem &x,uint16_t method,uint32_t off) { std::vector<uint8_t> o; CDRecord h=x.central; h.flags &= ~uint16_t(0x08); h.method=method; h.localHeaderOffset=off; appendBytes(o,&h,sizeof(h)); appendBytes(o,x.centralDynamic.data(),x.centralDynamic.size()); return o; }

std::vector<uint8_t> repack(const std::vector<uint8_t> &original,const std::vector<uint8_t> &zip,TomCryption &crypto) {
  g_stage=1; const size_t e=findEocd(original); const uint16_t commentLen=read16(original,e+20); std::vector<uint8_t> comment(original.begin()+e+22,original.end()); if(comment.size()!=commentLen) throw std::runtime_error("bad comment");
  g_stage=2; CryEngineDecryptionKeys keys=readKeys(comment,crypto);
  g_stage=3; auto items=parseZip(zip); if(items.size()>0xffff) throw std::runtime_error("too many files"); std::vector<uint8_t> out,cdr;
  for(auto &x:items){ g_stage=4; uint16_t localMethod=x.local.method; uint16_t centralMethod=encMethod(x.central.method); x.central.method=centralMethod; x.central.flags &= ~uint16_t(0x08); x.local.method=localMethod; x.local.flags &= ~uint16_t(0x08); x.local.descriptor=x.central.descriptor; uint32_t off=static_cast<uint32_t>(out.size()); auto local=serializeLocal(x,localMethod); unsigned char iv[BLOCK_CIPHER_KEY_LENGTH]; getInitialVector(x.central.descriptor,iv); int idx=getEncryptionKeyIndex(x.central.descriptor.crc); g_stage=5; auto el=crypt(crypto,local,keys.cipherKeyTable[idx],iv); auto ed=crypt(crypto,x.compressed,keys.cipherKeyTable[idx],iv); out.insert(out.end(),el.begin(),el.end()); out.insert(out.end(),ed.begin(),ed.end()); auto ch=serializeCentral(x,centralMethod,off); cdr.insert(cdr.end(),ch.begin(),ch.end()); }
  g_stage=6; uint32_t cdrOff=static_cast<uint32_t>(out.size()); auto ec=crypt(crypto,cdr,keys.cipherKeyTable[0],keys.cdrInitialVector); out.insert(out.end(),ec.begin(),ec.end()); CDREndRecord end{}; end.signature=0x06054b50u; end.entriesOnDisk=static_cast<uint16_t>(items.size()); end.entriesTotal=static_cast<uint16_t>(items.size()); end.size=static_cast<uint32_t>(cdr.size()); end.offset=cdrOff; end.commentLength=static_cast<uint16_t>(comment.size()); appendBytes(out,&end,sizeof(end)); out.insert(out.end(),comment.begin(),comment.end()); return out;
}
}

extern "C" DLLEXPORT int pak_repack(const char *encryptedPath,const char *sourceZipPath,const char *outputPath,const unsigned char *key,short keySize){
  try {
    if(!encryptedPath||!sourceZipPath||!outputPath||!key||keySize<=0) return ERROR_READ_KEY_FAILED;
    std::vector<uint8_t> a; try { a=readFile(encryptedPath); } catch(...) { return ERROR_FILE_NOT_FOUND; }
    std::vector<uint8_t> z; try { z=readFile(sourceZipPath); } catch(...) { return ERROR_FILE_NOT_FOUND; }
    TomCryption c; try { c.loadKeys(key,keySize); } catch(...) { return ERROR_READ_KEY_FAILED; }
    std::vector<uint8_t> o; try { o=repack(a,z,c); } catch(...) { return 20 + g_stage; }
    std::ofstream out(outputPath,std::ios::binary|std::ios::trunc); if(!out) return ERROR_FILE_NOT_FOUND;
    out.write(reinterpret_cast<const char*>(o.data()),static_cast<std::streamsize>(o.size())); return out?ERROR_NONE:ERROR_UNKNOWN;
  } catch(...) { return ERROR_UNKNOWN; }
}
