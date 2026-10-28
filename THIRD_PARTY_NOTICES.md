# Third-party software

XinPilot's license decision is separate from dependency licenses.

- PyParse: Apache-2.0; [upstream](https://github.com/thatchemistryguy/PyParse),
  [provenance](PyParse/PROVENANCE.md), [modifications](Modified%20PyParse/MODIFICATIONS.md).
- Ketcher 3.15.0: Apache-2.0; [upstream](https://github.com/epam/ketcher).
  Compiled editor assets are under ketcher_bridge/dist.
- RDKit: BSD-3-Clause; [upstream](https://www.rdkit.org/).
- pywebview: BSD-3-Clause; [upstream](https://github.com/r0x0r/pywebview).
- TypeScript: Apache-2.0; [upstream](https://github.com/microsoft/TypeScript).

Retained full license texts, including Python/Tk and Ketcher notices, are in
third_party/licenses. Installed Python packages retain their own distribution
metadata and licenses. requirements.txt identifies direct runtime dependencies;
PyInstaller is a build dependency with its own bootloader exception. Opentrons
and its labware data are dependencies of the simulator.

This source tree does not redistribute the Python environment or simulator binary.
An executable must carry applicable runtime license texts and notices; the spec
includes retained third-party notices. FASTSOLV/model weights remain external
and retain their upstream terms.
