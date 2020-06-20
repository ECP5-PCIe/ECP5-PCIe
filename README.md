# ECP5-PCIe
## ECP5 to PCIe interface development
The goal of this project is to provide a PCIe interface in nMigen.
## Previous work
There already exists a PCIe physical layer by whitequark called [Yumewatari](https://github.com/whitequark/Yumewatari) and a TLP and DMA layer by enjoy-digital called [litepcie](https://github.com/enjoy-digital/litepcie/tree/master/litepcie) written in omigen.

## TODO
- Read through Yumewatari and litepcie code
- Read more of the PCIe spec and summarize relevant parts
- Get an ECP5 device capable of PCIe
	- Currently an adapter for the ECP5 EVN to PCIe is being built

## INSTALL
Execute `python setup.py develop` in the Gateware folder

## SETUP
https://github.com/ECP5-PCIe/ECP5-PCIe/wiki/Setup