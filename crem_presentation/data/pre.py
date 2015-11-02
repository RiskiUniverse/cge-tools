
# coding: utf-8

# # Data preparation for CECP CoP21 website
# File locations:

# In[114]:

GDX_DIR = 'gdx'
OUT_DIR = '../../../cecp-cop21-data'


# ## 1. Run C-REM
# Run the next cell will run the model eight times, which takes a *very long time*. The commands are provided for illustration.
# 
# Currently, separate commits of C-REM must be used to run the base and 'less-GDP' cases.
# 
# See [issue #35](https://github.com/mit-jp/crem/issues/35).

# In[ ]:

get_ipython().run_cell_magic('bash', '', '# C-REM runs\ncrem gdx/result_urban_exo -- --case=default\ncrem gdx/result_cint_n_3 -- --case=cint_n --cint_n_rate=3\ncrem gdx/result_cint_n_4 -- --case=cint_n --cint_n_rate=4\ncrem gdx/result_cint_n_5 -- --case=cint_n --cint_n_rate=5\n# Low-growth cases\ncrem gdx/result_urban_exo_lessGDP -- --case=default\ncrem gdx/result_cint_n_3_lessGDP -- --case=cint_n --cint_n_rate=3\ncrem gdx/result_cint_n_4_lessGDP -- --case=cint_n --cint_n_rate=4\ncrem gdx/result_cint_n_5_lessGDP -- --case=cint_n --cint_n_rate=5')


# ## 2. Preprocess the GDX files
# Some of the quantities used below are stored in the GAMS parameters `report(*,*,*)` and `egyreport2(*,*,*,*)`, which pyGDX cannot handle. The cell below runs the simple GAMS script `pre.gms` to produce a new file named `*foo*_extra.gdx` with the pyGDX-friendly variables `ptcarb_t(t)`, `pe_t(e,r,t)` and `cons_t(r,t)`.

# In[17]:

get_ipython().run_cell_magic('bash', '', 'gams pre.gms --file=gdx/result_urban_exo\ngams pre.gms --file=gdx/result_cint_n_3\ngams pre.gms --file=gdx/result_cint_n_4\ngams pre.gms --file=gdx/result_cint_n_5\ngams pre.gms --file=gdx/result_urban_exo_lessGDP\ngams pre.gms --file=gdx/result_cint_n_3_lessGDP\ngams pre.gms --file=gdx/result_cint_n_4_lessGDP\ngams pre.gms --file=gdx/result_cint_n_5_lessGDP')


# ## 3. Read the GDX files

# In[253]:

# Load all the GDX files
import csv
from collections import OrderedDict
from os import makedirs as mkdir
from os.path import join

import gdx
from openpyxl import load_workbook
import pandas as pd
import xray

FILES = [
    ('bau', 'result_urban_exo.gdx'),
    ('3', 'result_cint_n_3.gdx'),
    ('4', 'result_cint_n_4.gdx'),
    ('5', 'result_cint_n_5.gdx'),
    ('bau_lo', 'result_urban_exo_lessGDP.gdx'),
    ('3_lo', 'result_cint_n_3_lessGDP.gdx'),
    ('4_lo', 'result_cint_n_4_lessGDP.gdx'),
    ('5_lo', 'result_cint_n_5_lessGDP.gdx'),
    ]

raw = OrderedDict()
extra = dict()
for case, fn in FILES:
    raw[case] = gdx.File('gdx/' + fn)
    extra[case] = gdx.File('gdx/' + fn.replace('.gdx', '_extra.gdx'))

CREM = raw['bau']
cases = pd.Index(raw.keys(), name='case')
time = pd.Index(filter(lambda t: int(t) <= 2030, CREM.set('t')))


# In[254]:

# List all the parameters available in each file
#CREM.parameters()

# Temporary container for read-in data
arrays = {}

def label(variable, desc, unit_long, unit_short):
    """Add some descriptive attributes to an xray.DataArray."""
    arrays[variable].attrs.update({'desc': desc, 'unit_long': unit_long,
                                   'unit_short': unit_short})


# In[255]:

# GDP
temp = [raw[case].extract('gdp_ref') for case in cases]
arrays['GDP'] = xray.concat(temp, dim=cases).sel(rs=CREM.set('r'))                     .rename({'rs': 'r'})
label('GDP', 'Gross domestic product',
      'billions of U.S. dollars, constant at 2007', '10⁹ USD')
arrays['GDP_delta'] = (arrays['GDP'] / arrays['GDP'].sel(case='bau') - 1) * 100
label('GDP_delta', 'Change in gross domestic product relative to BAU',
      'percent', '%')


# In[256]:

# CO2 emissions
temp = []
for case in cases:
    temp.append(raw[case].extract('sectem').sum('g') +
        raw[case].extract('houem'))
arrays['CO2_emi'] = xray.concat(temp, dim=cases)
label('CO2_emi', 'Annual CO₂ emissions',
      'millions of tonnes of CO₂', 'Mt')


# In[257]:

# Air pollutant emissions
temp = []
for case in cases:
    temp.append(raw[case].extract('urban').sum('*'))
temp = xray.concat(temp, dim=cases).sel(rs=CREM.set('r')).rename({'rs': 'r'})
for u in temp['urb']:
    if u in ['PM10', 'PM25']:
        continue
    var_name = '{}_emi'.format(u.values)
    arrays[var_name] = temp.sel(urb=u).drop('urb')
    u_fancy = str(u.values).translate({'2': '₂', '3': '₃'})
    label(var_name, 'Annual {} emissions'.format(u_fancy),
          'millions of tonnes of ' + str(u_fancy), 'Mt')


# In[258]:

# CO₂ price
temp = []
for case in cases:
    temp.append(extra[case].extract('ptcarb_t'))
arrays['CO2_price'] = xray.concat(temp, dim=cases)
label('CO2_price', 'Price of CO₂ emissions permit',
      '2007 US dollars per tonne CO₂', '2007 USD/t')


# In[259]:

# Consumption
temp = []
for case in cases:
    temp.append(extra[case].extract('cons_t'))
arrays['cons'] = xray.concat(temp, dim=cases)
label('cons', 'Household consumption',
      'billions of U.S. dollars, constant at 2007', '10⁹ USD')


# In[260]:

# Primary energy
temp = []
for case in cases:
    temp.append(extra[case].extract('pe_t'))
temp = xray.concat(temp, dim=cases)
temp = temp.where(temp < 1e300).fillna(0)
e_name = {
    'COL': 'Coal',
    'GAS': 'Natural gas',
    'OIL': 'Crude oil',
    'NUC': 'Nuclear',
    'WND': 'Wind',
    'SOL': 'Solar',
    'HYD': 'Hydroelectricity',
    }
for ener in temp['e']:
    var_name = '{}_energy'.format(ener.values)
    arrays[var_name] = temp.sel(e=ener).drop('e')
    label(var_name, 'Primary energy from {}'.format(e_name[str(ener.values)]),
          'millions of tonnes of coal equivalent', 'Mtce')

# Sums and shares 
arrays['energy_total'] = temp.sum('e')
label('energy_total', 'Primary energy, total',
      'millions of tonnes of coal equivalent', 'Mtce')

arrays['energy_fossil'] = temp.sel(e=['COL', 'GAS', 'OIL']).sum('e')
label('energy_fossil', 'Primary energy from fossil fuels',
      'millions of tonnes of coal equivalent', 'Mtce')

arrays['energy_nonfossil'] = temp.sel(e=['NUC', 'WND', 'SOL', 'HYD']).sum('e')
label('energy_nonfossil', 'Primary energy from non-fossil sources',
      'millions of tonnes of coal equivalent', 'Mtce')

arrays['energy_nonfossil_share'] = (arrays['energy_nonfossil'] /
    arrays['energy_total']) * 100
label('energy_nonfossil_share', 'Share of non-fossil sources in primary energy',
      'percent', '%')


# In[318]:

arrays['energy_nonfossil_share'].sel(case='bau', r='GD')


# In[261]:

# Population
temp = []
for case in cases:
    temp.append(raw[case].extract('pop2007').sel(g='c') *
                raw[case].extract('pop') * 1e-2)
arrays['pop'] = xray.concat(temp, dim=cases).drop('g').sel(rs=CREM.set('r'))                     .rename({'rs': 'r'})
label('pop', 'Population', 'millions', '10⁶')


# In[262]:

# Share of coal in production inputs
temp = []
for case in cases:
    y_in = raw[case].extract('sect_input')
    e_in = raw[case].extract('ye_input')
    nhw_in = raw[case].extract('ynhw_input')
    # Total coal input
    COL = y_in.sum('g').sel(**{'*': 'COL'}) + e_in.sel(**{'*': 'COL'})
    # Total of ELE inputs, to avoid double-counting
    ELE_in = e_in.sum('*') + nhw_in.sum('*')
    temp.append(COL / (y_in.sum(['*', 'g']) - ELE_in))
arrays['COL_share'] = xray.concat(temp, dim=cases).drop('*')                           .sel(rs=CREM.set('r')).rename({'rs': 'r'})
label('COL_share', 'Value share of coal in industrial production',
      '(unitless)', '0')


# ### PM2.5 population-weighted exposure
# **Note:** these are contained in a separate XLSX file:

# In[263]:

# Open the workbook and worksheet
wb = load_workbook('pm.xlsx', read_only=True)
ws = wb['Sheet1']


# In[264]:

# Read the table in to a list of lists
temp = []
cols = {
    None: 'None',
    2010: ('bau', '2010'),
    2030: ('bau', '2030'),
    '2030_p2': ('2', '2030'),
    '2030_p3': ('3', '2030'),
    '2030_p4': ('4', '2030'),
    '2030_p5': ('5', '2030'),
    '2030_p6': ('6', '2030'),
    }
for r, row in enumerate(ws.rows):
    if r < 1 or r > 31:
        pass
    elif r == 1:
        temp.append([cols[cell.value] for c, cell in enumerate(row) if c < 8])
    else:
        temp.append([cell.value for c, cell in enumerate(row) if c < 8])

# Convert to a pandas.DataFrame
df = pd.DataFrame(temp).set_index(0)
df.columns = pd.MultiIndex.from_tuples(df.iloc[0,:], names=['case', 't'])
df.drop('None', inplace=True)
df.index.name = 'r'
df = df.stack(['case', 't']).swaplevel('case', 'r')

# Convert to an xray.DataArray
da = xray.DataArray.from_series(df)
# Fill in 2010 values across cases
for c in da.coords['case']:
    da.loc[c,:,'2010'] = da.loc['bau',:,'2010']
arrays['PM25_exposure'] = da.drop(['2', '6'], dim='case')
label('PM25_exposure', 'Population-weighted exposure to PM2.5',
      'micrograms per cubic metre', 'μg/m³')

# TODO PM2.5 concentrations
# FIXME this is a placeholder
arrays['PM25_conc'] = arrays['PM25_exposure']
label('PM25_conc', 'Province-wide average PM2.5',
      'micrograms per cubic metre', 'μg/m³')


# In[319]:

# Combine all variables into a single xray.Dataset and truncate time
data = xray.Dataset(arrays).sel(t=time)

data['scenarios'] = xray.DataArray((
    'BAU: Business-as-usual',
    'Policy: Reduce carbon-intensity of GDP by 3%/year from BAU',
    'Policy: Reduce carbon-intensity of GDP by 4%/year from BAU',
    'Policy: Reduce carbon-intensity of GDP by 5%/year from BAU',
    'LO: BAU with 1% lower annual GDP growth',
    'Policy: Reduce carbon-intensity of GDP by 3%/year from LO',
    'Policy: Reduce carbon-intensity of GDP by 4%/year from LO',
    'Policy: Reduce carbon-intensity of GDP by 5%/year from LO',
    ), coords={'case': cases}, dims='case')

for var in [data.PM25_exposure, data.PM25_conc]:
    # FIXME fill in PM data for missing years
    var.loc[:,:,'2007'] = var.loc[:,:,'2010'] * 0.5
    var.loc[:,:,'2015'] = var.loc[:,:,'2030'] * 1.5
    var.loc[:,:,'2020'] = var.loc[:,:,'2030'] * 1.5
    var.loc[:,:,'2025'] = var.loc[:,:,'2030'] * 1.5
    # FIXME fill in PM data for missing cases
    var.loc['bau_lo',:,:] = var.loc['bau',:,:] * 0.9
    var.loc['3_lo',:,:] = var.loc['3',:,:] * 0.9
    var.loc['4_lo',:,:] = var.loc['4',:,:] * 0.9
    var.loc['5_lo',:,:] = var.loc['5',:,:] * 0.9

# TODO construct data for low-ammonia cases
#  - The NH3 *emissions* are not plotted; so this may not be necessary.
base_cases = [str(name.values) for name in data['case']] 
nh3_cases = [name + '_nh3' for name in base_cases]
d = xray.Dataset(coords={'case': nh3_cases})
data.merge(d, join='outer', inplace=True)

# FIXME fill in PM data for missing cases
for nh3_case, base_case in zip(nh3_cases, base_cases):
    data.PM25_conc.loc[nh3_case,:,:] = data.PM25_conc.loc[base_case,:,:]

# National totals
national = data.sum('r')
national['energy_nonfossil_share'] = (national.energy_nonfossil /
    national.energy_total) * 100
# FIXME use a proper national average
national['PM25_exposure'] = data.PM25_exposure.mean(dim='r')
national['PM25_conc'] = data.PM25_conc.mean(dim='r')


# ## 4. Output data

# In[320]:

# Output a file with scenario information
data['scenarios'].to_dataframe().to_csv(join(OUT_DIR, 'scenarios.csv'),
                                        header=['description'],
                                        quoting=csv.QUOTE_ALL)

# Output a file with variable information
var_info = pd.DataFrame(index=[d for d in data.data_vars if d != 'scenarios'],
                        columns=['desc', 'unit_long', 'unit_short'],
                       dtype=str)
print('Missing dimension info:')
for name, _ in var_info.iterrows():
    try:
        row = [data[name].attrs[k] for k in var_info.columns]
    except KeyError:
        print(' ', name)
        continue
    var_info.loc[name,:] = row
var_info.to_csv(join(OUT_DIR, 'variables.csv'), index_label='Variable',
                quoting=csv.QUOTE_ALL)

# Create directories
for r in CREM.set('r'):
    mkdir(join(OUT_DIR, r), exist_ok=True)
mkdir(join(OUT_DIR, 'national'), exist_ok=True)

# Serialize to CSV
for c in map(lambda x: x.values, data.case):
    # Provincial data
    for r in CREM.set('r'):
        data.sel(case=c, r=r).drop(['case', 'r', 'scenarios']).to_dataframe()            .to_csv(join(OUT_DIR, r, '{}.csv'.format(c)))
    # National data
    national.sel(case=c).drop(['case', 'scenarios']).to_dataframe()             .to_csv(join(OUT_DIR, 'national', '{}.csv'.format(c)))

