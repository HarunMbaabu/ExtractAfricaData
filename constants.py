import re

COUNTRIES = [
    "Algeria","Angola","Benin","Botswana","Burkina Faso","Burundi","Cameroon",
    "Cape Verde","Central African Republic","Chad","Comoros","Congo Democratic Republic",
    "Congo Republic","Cote d'Ivoire","Djibouti","Egypt","Equatorial Guinea","Eritrea",
    "Eswatini","Ethiopia","Gabon","Gambia","Ghana","Guinea","Guinea Bissau","Kenya",
    "Lesotho","Liberia","Libya","Madagascar","Malawi","Mali","Mauritania","Mauritius",
    "Morocco","Mozambique","Namibia","Niger","Nigeria","Rwanda","Sao Tome and Principe",
    "Senegal","Seychelles","Sierra Leone","Somalia","South Africa","South Sudan","Sudan",
    "Tanzania","Togo","Tunisia","Uganda","Zambia","Zimbabwe"
]

WDI_AFR_ISO3 = {
    "DZ":"Algeria","AO":"Angola","BJ":"Benin","BW":"Botswana","BF":"Burkina Faso","BI":"Burundi","CM":"Cameroon",
    "CV":"Cape Verde","CF":"Central African Republic","TD":"Chad","KM":"Comoros","CD":"Congo Democratic Republic",
    "CG":"Congo Republic","CI":"Cote d'Ivoire","DJ":"Djibouti","EG":"Egypt","GQ":"Equatorial Guinea","ER":"Eritrea",
    "SZ":"Eswatini","ET":"Ethiopia","GA":"Gabon","GM":"Gambia","GH":"Ghana","GN":"Guinea","GW":"Guinea Bissau",
    "KE":"Kenya","LS":"Lesotho","LR":"Liberia","LY":"Libya","MG":"Madagascar","MW":"Malawi","ML":"Mali",
    "MR":"Mauritania","MU":"Mauritius","MA":"Morocco","MZ":"Mozambique","NA":"Namibia","NE":"Niger","NG":"Nigeria",
    "RW":"Rwanda","ST":"Sao Tome and Principe","SN":"Senegal","SC":"Seychelles","SL":"Sierra Leone","SO":"Somalia",
    "ZA":"South Africa","SS":"South Sudan","SD":"Sudan","TZ":"Tanzania","TG":"Togo","TN":"Tunisia","UG":"Uganda",
    "ZM":"Zambia","ZW":"Zimbabwe"
}

PREFERRED_TO_COUNTRIES = {
    "Cabo Verde":"Cape Verde",
    "Central Africa Rep.":"Central African Republic",
    "Côte d'Ivoire":"Cote d'Ivoire",
    "Eq. Guinea":"Equatorial Guinea",
    "São Tomé and Príncipe":"Sao Tome and Principe",
    "S. Sudan":"South Sudan",
    "democratic republic of the congo": "Congo Democratic Republic",
    "republic of the congo": "Congo Republic",
    "guinea-bissau": "Guinea Bissau",
    "tanzania, united republic of": "Tanzania",
    "United Republic of Tanzania": "Tanzania",
    "Democratic Republic of the Congo": "Congo Democratic Republic",
    "Congo": "Congo Republic",
    "congo": "Congo Republic", 
    "democratic republic of the congo": "Congo Democratic Republic",
    "guinea-bissau": "Guinea Bissau",
    "united republic of tanzania": "Tanzania",
    "northern africa": None,
    "Guinea-Bissau": "Guinea Bissau",
    "Gambia, The": "Gambia",
    "Egypt, Arab Rep.": "Egypt",
    "Congo Rep.": "Congo Republic",
    "Congo, Rep.": "Congo Republic",
    "Congo, Dem. Rep.": "Congo Democratic Republic",
    "Congo, Democratic Republic of the": "Congo Democratic Republic",
    "Somalia, Fed. Rep.": "Somalia",
    "Cote d'Ivoire": "Cote d'Ivoire",
    "Côte d’Ivoire": "Cote d'Ivoire",
}

SYNONYMS = {
    "cabo verde":"Cape Verde",
    "cape verde":"Cape Verde",
    "central africa rep.":"Central African Republic",
    "central african republic":"Central African Republic",
    "cote d'ivoire":"Cote d'Ivoire",
    "côte d'ivoire":"Cote d'Ivoire",
    "equatorial guinea":"Equatorial Guinea",
    "eq. guinea":"Equatorial Guinea",
    "sao tome and principe":"Sao Tome and Principe",
    "são tomé and príncipe":"Sao Tome and Principe",
    "south sudan":"South Sudan",
    "s. sudan":"South Sudan",
    "Côte d’Ivoire":"Cote d'Ivoire",
}

ENERGY_INDICATORS = [
    "Population access to electricity-National (% of population)",
    "Population access to electricity-Rural (% of population)",
    "Population access to electricity-Urban (% of population)",
    "Population with access to electricity-National (millions of people)",
    "Population with access to electricity-Rural (millions of people)",
    "Population with access to electricity-Urban (millions of people)",
    "Population without access to electricity-National (millions of people)",
    "Population without access to electricity-Rural (millions of people)",
    "Population without access to electricity-Urban (millions of people)",
    "Electricity export (GWh)",
    "Electricity final consumption (GWh)",
    "Electricity final consumption per capita (KWh)",
    "Electricity generated from biofuels and waste (GWh)",
    "Electricity generated from fossil fuels (GWh)",
    "Electricity generated from geothermal energy (GWh)",
    "Electricity generated from hydropower (GWh)",
    "Electricity generated from nuclear power (GWh)",
    "Electricity generated from renewable sources (GWh)",
    "Electricity generated from solar, wind, tide, wave and other sources (GWh)",
    "Electricity generation per capita (KWh)",
    "Electricity generation, Total (GWh)",
    "Electricity import (GWh)",
    "Electricity: Net imports ( GWh )",
    "Electricity installed capacity in Bioenergy (MW)",
    "Electricity installed capacity in Fossil fuels (MW)",
    "Electricity installed capacity in Geothermal (MW)",
    "Electricity installed capacity in Hydropower (MW)",
    "Electricity installed capacity in Non-renewable energy (MW)",
    "Electricity installed capacity in Nuclear (MW)",
    "Electricity installed capacity in Solar (MW)",
    "Electricity installed capacity in Total renewable energy (MW)",
    "Electricity installed capacity in Wind (MW)",
    "Electricity installed capacity in other Non-renewable energy (MW)",
    "Electricity installed capacity, Total (MW)"
]

WDI_INDICATORS = {
  "EG.FEC.RNEW.ZS": "Renewable energy consumption (% of total final energy consumption)",
  "EG.ELC.RNEW.ZS": "Renewable electricity output (% of total electricity output)",
  "IE.PPN.ENGY.CD": "Public private partnerships investment in energy (current US$)",
  "EN.GHG.N2O.TR.MT.CE.AR5": "Nitrous oxide (N2O) emissions from Transport (Energy) (Mt CO2e)",
  "EN.GHG.N2O.PI.MT.CE.AR5": "Nitrous oxide (N2O) emissions from Power Industry (Energy) (Mt CO2e)",
  "EN.GHG.N2O.IC.MT.CE.AR5": "Nitrous oxide (N2O) emissions from Industrial Combustion (Energy) (Mt CO2e)",
  "EN.GHG.N2O.FE.MT.CE.AR5": "Nitrous oxide (N2O) emissions from Fugitive Emissions (Energy) (Mt CO2e)",
  "EN.GHG.N2O.BU.MT.CE.AR5": "Nitrous oxide (N2O) emissions from Building (Energy) (Mt CO2e)",
  "EN.GHG.CH4.TR.MT.CE.AR5": "Methane (CH4) emissions from Transport (Energy) (Mt CO2e)",
  "EN.GHG.CH4.PI.MT.CE.AR5": "Methane (CH4) emissions from Power Industry (Energy) (Mt CO2e)",
  "EN.GHG.CH4.IC.MT.CE.AR5": "Methane (CH4) emissions from Industrial Combustion (Energy) (Mt CO2e)",
  "EN.GHG.CH4.FE.MT.CE.AR5": "Methane (CH4) emissions from Fugitive Emissions (Energy) (Mt CO2e)",
  "EN.GHG.CH4.BU.MT.CE.AR5": "Methane (CH4) emissions from Building (Energy) (Mt CO2e)",
  "IE.PPI.ENGY.CD": "Investment in energy with private participation (current US$)",
  "EG.GDP.PUSE.KO.PP": "GDP per unit of energy use (PPP $ per kg of oil equivalent)",
  "EG.GDP.PUSE.KO.PP.KD": "GDP per unit of energy use (constant 2021 PPP $ per kg of oil equivalent)",
  "EG.USE.COMM.FO.ZS": "Fossil fuel energy consumption (% of total)",
  "IC.FRM.ENGM.ZS": "Firms adopting energy management measures to reduce emissions (% of firms)",
  "EG.USE.COMM.GD.PP.KD": "Energy use (kg of oil equivalent) per $1,000 GDP (constant 2021 PPP)",
  "EG.USE.PCAP.KG.OE": "Energy use (kg of oil equivalent per capita)",
  "EG.EGY.PRIM.PP.KD": "Energy intensity level of primary energy (MJ/$2017 PPP GDP)",
  "EG.IMP.CONS.ZS": "Energy imports, net (% of energy use)",
  "EG.ELC.RNWX.KH": "Electricity production from renewable sources, excluding hydroelectric (kWh)",
  "EG.ELC.RNWX.ZS": "Electricity production from renewable sources, excluding hydroelectric (% of total)",
  "EG.ELC.FOSL.ZS": "Electricity production from oil, gas and coal sources (% of total)",
  "EG.ELC.PETR.ZS": "Electricity production from oil sources (% of total)",
  "EG.ELC.NUCL.ZS": "Electricity production from nuclear sources (% of total)",
  "EG.ELC.NGAS.ZS": "Electricity production from natural gas sources (% of total)",
  "EG.ELC.HYRO.ZS": "Electricity production from hydroelectric sources (% of total)",
  "EG.ELC.COAL.ZS": "Electricity production from coal sources (% of total)",
  "EG.USE.CRNW.ZS": "Combustible renewables and waste (% of total energy)",
  "EN.GHG.CO2.TR.MT.CE.AR5": "Carbon dioxide (CO2) emissions from Transport (Energy) (Mt CO2e)",
  "EN.GHG.CO2.PI.MT.CE.AR5": "Carbon dioxide (CO2) emissions from Power Industry (Energy) (Mt CO2e)",
  "EN.GHG.CO2.IC.MT.CE.AR5": "Carbon dioxide (CO2) emissions from Industrial Combustion (Energy) (Mt CO2e)",
  "EN.GHG.CO2.FE.MT.CE.AR5": "Carbon dioxide (CO2) emissions from Fugitive Emissions (Energy) (Mt CO2e)",
  "EN.GHG.CO2.BU.MT.CE.AR5": "Carbon dioxide (CO2) emissions from Building (Energy) (Mt CO2e)",
  "EG.USE.COMM.CL.ZS": "Alternative and nuclear energy (% of total energy use)",
  "NY.ADJ.DNGY.CD": "Adjusted savings: energy depletion (current US$)",
  "NY.ADJ.DNGY.GN.ZS": "Adjusted savings: energy depletion (% of GNI)",
  "EG.ELC.ACCS.UR.ZS": "Access to electricity, urban (% of urban population)",
  "EG.ELC.ACCS.RU.ZS": "Access to electricity, rural (% of rural population)",
  "EG.ELC.ACCS.ZS": "Access to electricity (% of population)",
  "EG.CFT.ACCS.UR.ZS": "Access to clean fuels and technologies for cooking, urban (% of urban population)",
  "EG.CFT.ACCS.RU.ZS": "Access to clean fuels and technologies for cooking, rural (% of rural population)",
  "EG.CFT.ACCS.ZS": "Access to clean fuels and technologies for cooking (% of population)"
}

def _strip_number_prefix(s: str) -> str:
    return re.sub(r"^\s*\d+\s*[-–)\.]?\s*", "", s)

def _collapse_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def normalize_country(name: str) -> str | None:
    if not name:
        return None
    s = str(name).strip().strip(",;")
    if not s:
        return None
    s = _strip_number_prefix(s)
    s = _collapse_spaces(s)
    if len(s) == 2 and s.isalpha():
        mapped = WDI_AFR_ISO3.get(s.upper())
        if mapped:
            return mapped
    key = s.lower()
    if key in SYNONYMS:
        return SYNONYMS[key]
    titled = s
    if titled in PREFERRED_TO_COUNTRIES:
        return PREFERRED_TO_COUNTRIES[titled]
    if titled in COUNTRIES:
        return titled
    return titled

COUNTRY_TO_SERIAL = {c: i + 1 for i, c in enumerate(COUNTRIES)}

def serial_for_country(name: str) -> int | None:
    n = normalize_country(name)
    return COUNTRY_TO_SERIAL.get(n)
