# libcrypak backend

This directory contains the MIT-licensed `libcrypak` source used by the
`cry-pak-repack.dll` backend. The backend preserves the source CryEngine
encryption comment and re-encrypts rebuilt ZIP members with the source pak's
Twofish-CTR key table and CDR IV.

## Build on Windows

Requirements: CMake 3.14+, Visual Studio 2022, Git, and an internet connection
for the pinned fmt/libtommath/libtomcrypt ExternalProject dependencies.

```powershell
cmake -S native/libcrypak -B native/libcrypak/build -G "Visual Studio 17 2022" -A x64
cmake --build native/libcrypak/build --config Release
Copy-Item native/libcrypak/build/src/Release/libcrypak.dll resources/bin/cry-pak-repack.dll
```

The DLL exports the original decryption API plus `pak_repack`. The Python CLI
loads it through `adapters/pak_crypak.py` and stages paths in an ASCII temporary
directory for Windows compatibility.
