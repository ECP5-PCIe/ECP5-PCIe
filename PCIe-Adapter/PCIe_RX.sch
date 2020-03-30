EESchema Schematic File Version 4
EELAYER 30 0
EELAYER END
$Descr A4 11693 8268
encoding utf-8
Sheet 3 3
Title ""
Date ""
Rev ""
Comp ""
Comment1 ""
Comment2 ""
Comment3 ""
Comment4 ""
$EndDescr
$Comp
L PCIe:PCIe_x4 J?
U 4 1 5E8456BF
P 4200 3450
AR Path="/5E8456BF" Ref="J?"  Part="4" 
AR Path="/5E8420DD/5E8456BF" Ref="J1"  Part="4" 
F 0 "J1" H 4142 3625 50  0000 C CNN
F 1 "PCIe_x4" H 4142 3534 50  0000 C CNN
F 2 "" H 3650 3450 50  0001 C CNN
F 3 "" H 3650 3450 50  0001 C CNN
	4    4200 3450
	-1   0    0    -1  
$EndComp
$Comp
L PCIe:ECP5_EVN_PCIe U?
U 2 1 5E8456C5
P 5800 3450
AR Path="/5E8456C5" Ref="U?"  Part="2" 
AR Path="/5E8420DD/5E8456C5" Ref="U2"  Part="2" 
F 0 "U2" H 6028 2943 50  0000 L CNN
F 1 "ECP5_EVN_PCIe" H 6028 2852 50  0000 L CNN
F 2 "" H 5600 3500 50  0001 C CNN
F 3 "" H 5600 3500 50  0001 C CNN
	2    5800 3450
	1    0    0    -1  
$EndComp
Wire Wire Line
	4500 4400 5500 4400
Wire Wire Line
	5500 4300 4500 4300
Wire Wire Line
	4500 4200 5500 4200
Wire Wire Line
	5500 4100 4500 4100
Wire Wire Line
	4500 4000 5500 4000
Wire Wire Line
	5500 3900 4500 3900
Wire Wire Line
	4500 3800 5500 3800
Wire Wire Line
	5500 3700 4500 3700
Text HLabel 4500 3500 2    50   Output ~ 0
REFPCIe+
Text HLabel 4500 3600 2    50   Output ~ 0
REFPCIE-
Text HLabel 5500 3500 0    50   Input ~ 0
REFECP+
Text HLabel 5500 3600 0    50   Input ~ 0
REFECP-
Text Label 5000 3700 1    50   ~ 0
RX0+
Text Label 5100 3800 1    50   ~ 0
RX0-
Text Label 4900 3900 1    50   ~ 0
RX1+
Text Label 5200 4200 1    50   ~ 0
RX2-
Text Label 5100 4100 1    50   ~ 0
RX2+
Text Label 5400 4400 1    50   ~ 0
RX3-
Text Label 5300 4300 1    50   ~ 0
RX3+
Text Label 5000 4000 1    50   ~ 0
RX1-
$EndSCHEMATC
