
from scoc_monitoring.services.noon_report_parser import parse_noon_report


sample = """

 	HELEN N - NOON
						
Daily Noon Report   01-SEP-2026						
Date / Time (LT / UTC)	01-Sep-2026 / 1200 LT / 0400 Z	 	 
Position 	24 24 N / 122 25 E
Course	010 deg
Average Speed	12.88 Knots	 	Draft F/A: 21.51m/21.86 m
Slip	12.06 %
Distance run / Distance to go	309 NM / 390 NM
Hours run 	24 Hours
Wind - Dir / Force	SE X 5
Sea State	MOD
Swell / Rolling / Pitching 	MOD/SLIGHT/SLIGHT
Current (Dir / Rate)	NE X 0.5 kts
Visibility / Range / Rain	GOOD/12 NM/05 HRS
ETA / Port 	02-SEPT-2026, 2300 LT AGW WP / SHULANGHU, CHINA 
Additional Information:						
RPM	64.3 rpm
F O 3.5 % Consumption	M / E	59.1 MT	A / E	2.8 MT 	Boiler	0 MT
F O 0.5 % Consumption	M / E	0 MT	A / E	0 MT	Boiler	0 MT
F O 0.1 % Consumption	M / E	0 MT	A / E	0.1 MT	Boiler	0 MT
M/E Consumption per mile	0.191 MT / mile
M/E Load % MCR	52.83 %  /  11993 kW
Eco Diff Press	55 mm H2O
M/E Exh Gas Temp avg	353 Deg C
M/E L O Pressure	2.9 Kg/cm2
M/E L O Outlet Temp avg	58 deg C
M/E Jkt Outlet Temp avg	83 deg C
Scavenge Temp	45 deg C
Bunker ROB  MT	0.1%	248.2 MT	0.5%	0 MT	3.5%	1088.2 MT
M/E Cyl oil cons per  24hrs /specific	284 Ltrs	0.918 gm / Kw-hr
F O Sulphur Content / HMI Settings	3.46%	0.80gm / Kw-hr
M/E F O Inlet Temp / Viscosity	131 deg C	12.5 cst
A/E 1 - A/E2 - A/E3 - kW / Load	A/E1	300/430	A/E2	  0 / 0  	A/E3	280/420
Sludge Gen / Incin+Evap / ROB	0.5 m3 	0.4 m3 	6.8 m3 
Remarks	 
	 ME FUEL OPT SET AT POWER MODE (12000KW)
	 

48 Hrs Noon Report	 
Date / Time (LT / UTC)	01-Sep-2026 / 1200 LT / 0400 Z
Position	24 24 N / 122 25 E
Rpm / Slip / kW	64.26 / 14.57% / 12278 Kw
Bunker ROB	0.1%	248.2 MT	3.50%	1088.2 MT	0.5%	0 MT
Avg.Cons /day (48 hours)	0.1%	0.1 MT	3.50%	61.55 MT	0.5%	0 MT
Avg. Cons (SOP)	0.1%	0.17 MT	3.50%	59.77 MT	0.5%	#VALUE!
Avg.Speed (48 hours)	12.50 Knots
Avg. Speed (SOP)	11.59 Knots
Weather / Wind / Sea Cond.	O’CAST / SE X 5 / MOD
Miles to go to next port	390 NM
ETA / Port 	02-SEPT-2026, 2300 LT AGW WP / SHULANGHU, CHINA 
Remarks	

Thanks & Brgds,
Capt.Vinay Singh / CE S. Chatterjee
M.V. HELEN N
TEL: +49 40 87407098(VSAT)
TEL: +870 773061582(FBB)
TLX: 463710361
EMAIL: master@helenn.neufleet.com



Gen Ave Speed Voyage -11.86kts

Total Dist. Run Voyage-7168nm

Eng Distance - 315.91

Eng Speed - 13.16

RPM - 59.22

Slip - 17.07%

F. F.O Cons Last 24.0hrs -43.0MT
(ME-43.0MT- AE- 0.0MT + BLR- 0.0 )

ROB - HSFO 839.2MT

G. LSMGO Cons Last 24.0hrs - 0.0
ROB - LSMGO 172.5MT

Estimated Engine Power : 77%

Shaft power KW - 10800

Cyl Oil Cons 24.0hrs -265 Liters

Remarks:
Near Gale, Very Rough Sea, Vessel Rolling Moderately.
"""


result = parse_noon_report(sample)


for key, value in result.items():
    print(f"{key}: {value}")

