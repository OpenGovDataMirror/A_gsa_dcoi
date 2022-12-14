from __future__ import print_function

import csv
import sys
import itertools
import re
import io
import numpy as np
import pandas as pd
import pprint
import os
import warnings
warnings.filterwarnings('ignore')
try:
	filename = sys.argv[1]
except IndexError:
	print ('No filename specified!')
	exit()

print ('Filename: ', filename)

# Constant to define allowed values for a field
VALID_VALUES = {
	"Record Validity": ['Invalid Facility', 'Valid Facility'],
	"Ownership Type": ['Agency Owned', 'Colocation', 'Outsourcing', 'Using Cloud Provider'],
	"Inter-Agency Shared Services Position": ['Provider', 'Tenant', 'None'],
	"Country": ['U.S.', 'Outside U.S.'],
	"Data Center Tier": ['Non-Tiered', 'Tier 1', 'Tier 2', 'Tier 3', 'Tier 4', 'Unknown', 'Using Cloud Provider'],
	"Key Mission Facility": ['Yes', 'No'],
	"Key Mission Facility Type": ['Mission', 'Processing', 'Control', 'Location', 'Legal', 'Other'],
	"Electricity Is Metered": ['Yes', 'No'],
	"Closing Fiscal Year": [str(i) for i in range(2010, 2022)], # 2010 - 2021
	"Closing Quarter": ['Q1', 'Q2', 'Q3', 'Q4'],
	"Closing Stage": ['Closed', 'Migration Execution', 'Not closing'],
}

# Constant to define functions to check field value format
VALID_FUNCTIONS = {
	'Gross Floor Area': ['is_integer', 'greater_0'],
	'Avg Electricity Usage': ['is_decimal', 'greater_0'],
	'Avg IT Electricity Usage': ['is_decimal', 'greater_0'],
	'Underutilized Servers': ['is_integer', 'equal_greater_0'],
	'Actual Hours of Facility Downtime': ['is_integer', 'equal_greater_0'],
	'Planned Hours of Facility Availability': ['is_integer', 'equal_greater_0'],
	'Rack Count': ['is_integer', 'equal_greater_0'],
	'Total Mainframes':['is_integer', 'equal_greater_0'],
	'Total HPC Cluster Nodes': ['is_integer', 'equal_greater_0'],
	'Total Virtual Hosts': ['is_integer', 'equal_greater_0'],
}

# Variables we will re-use

hasErrors = False
hasWarnings = False

# Lowercase the field keys by updating the header row, for maximum compatiblity.
def lower_headings(iterator):
		return itertools.chain([next(iterator).lower()], iterator)

# must be an integer, e.g. "10", "-7"
def is_integer(value):
	try:
		int(value)
	except ValueError:
		return "must be an integer value"

# must be a float, e.g. "10", "-7.6"
def is_decimal(value):
	try:
		float(value)
	except ValueError:
		return "must be an float value"

# must be greater than 0, e.g. "0.1", "5"
def greater_0(value):
	try:
		assert float(value) > 0
	except ValueError:
		return "must be greater than 0"
	except AssertionError:
		return "must be greater than 0"

# must be equal or greater than 0, e.g. "0", "0.0", "10"
def equal_greater_0(value):
	try:
		assert float(value) >= 0
	except ValueError:
		return "must be greater than or equal to 0"
	except AssertionError:
		return "must be greater than or equal to 0"

# check field to against its valid_values/_functions
def validate_values(data, field, msg=''):
	errors = []
	value = data.get(field.lower(), '')

	# this function is not responsible to blank check
	if not value:
		return []

	# check against a list of values first
	if VALID_VALUES.get(field):
		values = VALID_VALUES.get(field)
		if value.lower() not in map(str.lower, values):
			msg = msg or 'If not blank, {} value must be one of "{}"; "{}" is given.'.format(field, '", "'.join(values), value)
			errors.append(msg)
	# then check with a list of functions
	elif VALID_FUNCTIONS.get(field):
		funcs = VALID_FUNCTIONS.get(field)
		errs = []
		for func in funcs:
			if not func:
				continue
			elif not isinstance(func, str):
				print('Provide a function name in function list for field "{}". {} is given.'.format(field, type(func)))
				exit()

			try:
				errs.append(eval(func)(value))
			except NameError:
				print('Function "{}" is not defined for field "{}".'.format(func, field))
				exit()

		# remove empty ones
		errs = [x for x in errs if x]

		if errs:
			msg = msg or field + ' ' + ', '.join(errs) + '. "' + value + '" is given.'
			errors.append(msg)

	return errors

# Check field for required
def validate_required(data, field, specials, msg=''):
	errors = []
	# check required implies check valid values first
	errors.extend(validate_values(data, field, msg))

	if errors:
		# if error from validate_values(), it means it HAS some value
		# so we skip blank check.
		pass
	if specials and field not in specials:
		pass
	elif not data.get(field.lower()):
		errors.append(msg or '{} must not be blank.'.format(field))

	return errors

# Main function starts
with io.open(filename, 'r', encoding='iso-8859-1') as datafile:
	reader = csv.DictReader(lower_headings(datafile))
	# added 'data center id' header as it was corrupted during recode/encode for some reason
	reader.fieldnames=['data center id', 'agency abbreviation', 'component', 'record validity', 'data center name',
						'published name', 'ownership type', 'inter-agency shared services position',
						'data center tier', 'country', 'gross floor area', 'key mission facility', 'key mission facility type',
						'optimization exempt', 'electricity is metered', 'avg electricity usage', 'avg it electricity usage',
						'underutilized servers', 'actual hours of facility downtime', 'planned hours of facility availability',
						'rack count', 'total mainframes', 'total hpc cluster nodes', 'total server count', 'total virtual hosts',
						'closing stage', 'closing fiscal year', 'closing quarter', 'comments', 'omb comments']
	stats = {
		'record_total': 0,
		'record_error': 0,
		'record_warning': 0,
		'error': 0,
		'warning': 0
	}

	#i nitiate a dictionary to store all information from the looping process
	agency_dict={}

	for row in reader:
		num = reader.line_num
		errors = []
		warnings = []
		
		#if num==1:
		#	#next(row,None)
		#	continue
		#else:
		#	pass

		###
		# Special conditions for required fields.
		###
		specials = []
		if row.get('record validity', '').lower() == 'invalid facility':
			specials = ['agency abbreviation', 'component', 'data center id', 'record validity']

		elif row.get('ownership type', '').lower() != 'agency owned':
			specials = ['agency abbreviation', 'component', 'data center id', 'record validity', 'closing stage']

		elif row.get('inter-agency shared services position', '').lower() == 'tenant':
			specials = ['agency abbreviation', 'component', 'data center id', 'record validity', 'closing stage', 'ownership type']

		elif row.get('key mission facility', '').lower() == 'yes':
			specials = ['agency abbreviation', 'component', 'data center id', 'record validity', 'closing stage', 'ownership type', 'key mission facility type']

		###
		# Data acceptance rules. These should match the IDC instructions.
		###

		# Common required checks
		#
		for required_field in ['Agency Abbreviation', 'Component', 'Data Center Name', 'Record Validity',
				'Ownership Type', 'Gross Floor Area', 'Data Center Tier', 'Key Mission Facility', 'Electricity Is Metered',
				'Underutilized Servers', 'Actual Hours of Facility Downtime', 'Planned Hours of Facility Availability',
				'Rack Count', 'Total Mainframes', 'Total HPC Cluster Nodes', 'Total Virtual Hosts', 'Closing Stage',
		]:
			errors.extend(validate_required(row, required_field, specials))

		# Common optional value checks
		#
		errors.extend(validate_values(row, 'Country'))

		# Other checks
		#
		if row.get('data center id') and not (re.match(r"DCOI-DC-\d+$", row.get('data center id'))):
				errors.append('Data Center ID must be DCOI-DC-#####. Or leave blank for new data centers.')

		if row.get('record validity', '').lower() == 'invalid facility' and row.get('closing stage').lower() == 'closed':
				errors.append('Record Validity cannot be "Invalid Facility" if Closing Stage is "Closed".')

		if row.get('ownership type', '').lower() == 'Using Cloud Provider'.lower() and row.get('data center tier', '').lower() != 'Using Cloud Provider'.lower():
				errors.append('Data Center Tier must be "Using Cloud Provider" if Ownership Type is "Using Cloud Provider".')

		if row.get('ownership type', '').lower() == 'Colocation'.lower():
			msg = 'Inter-Agency Shared Services Position must not be blank if Ownership Type is "Colocation".'
			errors.extend(validate_required(row, 'Inter-Agency Shared Services Position', specials, msg))
		else:
			errors.extend(validate_values(row, 'Inter-Agency Shared Services Position'))

		if row.get('key mission facility', '').lower() == 'yes':
			msg = 'Key Mission Facilities must have a Key Mission Facility Type.'
			errors.extend(validate_required(row, 'Key Mission Facility Type', specials, msg))
		else:
			errors.extend(validate_values(row, 'Key Mission Facility Type'))

		if row.get('electricity is metered', '').lower() == 'yes':
			msg = 'Avg Electricity Usage must not be blank if Electricity is Metered.'
			errors.extend(validate_required(row, 'Avg Electricity Usage', specials, msg))
			msg = 'Avg IT Electricity Usage must not be blank if Electricity is Metered.'
			errors.extend(validate_required(row, 'Avg IT Electricity Usage', specials, msg))
		else:
			errors.extend(validate_values(row, 'Avg Electricity Usage'))
			errors.extend(validate_values(row, 'Avg IT Electricity Usage'))

		# test the string is decimal then compare the value
		if row.get('avg electricity usage', '').replace('.','',1).isdigit() and row.get('avg it electricity usage', '').replace('.','',1).isdigit():
			if float(row.get('avg electricity usage')) < float(row.get('avg it electricity usage')):
				errors.append('Avg IT Electricity Usage must be less than or equal to Avg Electricity Usage.')

		if row.get('closing stage', '').lower() != 'not closing':
			msg = 'Closing Fiscal Year must not be blank if Closing Stage is not "Not Closing".'
			errors.extend(validate_required(row, 'Closing Fiscal Year', specials, msg))
			msg = 'Closing Quarter must not be blank if Closing Stage is not "Not Closing".'
			errors.extend(validate_required(row, 'Closing Quarter', specials, msg))
		else:
			errors.extend(validate_values(row, 'Closing Fiscal Year'))
			errors.extend(validate_values(row, 'Closing Quarter'))

		###
		# Data validation rules. This should catch any bad data.
		###

		if (row.get('record validity', '').lower() == 'valid facility' and
				row.get('closing stage', '').lower() != 'closed' and
				row.get('ownership type', '').lower() == 'agency owned' and
				row.get('data center tier', '').lower() not in map(str.lower, VALID_VALUES['Data Center Tier'])):
			warnings.append('Only tiered data centers need to be reported, marked as "{}"'.format(row.get('data center tier')))


		# Impossible PUEs

		# PUE = 1.0:
		if (row.get('avg electricity usage') and
				row.get('avg it electricity usage') and
				row.get('avg electricity usage') == row.get('avg it electricity usage')):

			warnings.append(
				'Avg Electricity Usage ({}) for a facility should never be equal to Avg IT Electricity Usage ({})'
					.format(row.get('avg electricity usage'), row.get('avg it electricity usage'))
			)

		# If Electricity is Metered = "No" then Electricity Usage should be blank
		if row.get('electricity is metered', '').lower() == 'no':
			if row.get('avg electricity usage'):
				warnings.append('Avg Electricity Usage should be blank if Electricity is not Metered.')
			if row.get('avg it electricity usage'):
				warnings.append('Avg IT Electricity Usage should be blank if Electricity is not Metered.')

		# Check for incorrect KMF reporting
		if row.get('key mission facility type') and row.get('key mission facility', '').lower() != 'yes':
			warnings.append('Key Mission Facility Type should only be present if Key Mission Facility is "Yes"')

		if row.get('key mission facility', '').lower() == 'yes':
			if row.get('data center tier', '').lower() not in map(str.lower, VALID_VALUES['Data Center Tier']):
				warnings.append('Key Mission Facilities should not be non-tiered data centers.')

			if row.get('ownership type', '').lower() != 'agency owned':
				warnings.append('Key Mission Facilities should only be agency-owned.')

			if row.get('record validity', '').lower() != 'valid facility':
				warnings.append('Invalid facilities should not be Key Mission Facilities.')

			if row.get('closing stage', '').lower() != 'closed':
				warnings.append('Key Mission Facilities cannot be "Yes" if Closing Stage is "Closed".')

		###
		# Print our results.
		###

		if len(errors) or len(warnings):
			# Print some sort of name to look up, even if we don't have one.

			if row.get('agency abbreviation'):
				agency_abrv=row.get('agency abbreviation')
			if row.get('component'):
				agency_comp=row.get('component')
			if row.get('data center id'):
				dc_id=row.get('data center id')
			else:
				pass

		if len(errors) > 0:

			hasErrors = True

		if len(warnings) > 0:
			hasWarnings = True
			
		# as the csv is being looped through the errors and warnings are being added to a dictionary
		# if the dictionary key value exists, it appends the message.  If it does not the key/value pair is created
		# this is editing agency_dict which was declared outside the for loop (line )

		if agency_abrv in agency_dict.keys():
			if agency_comp in agency_dict[agency_abrv].keys():
				if dc_id in agency_dict[agency_abrv][agency_comp].keys():
					agency_dict[agency_abrv][agency_comp][dc_id]['errors'].extend(errors)
					agency_dict[agency_abrv][agency_comp][dc_id]['warnings'].extend(warnings)
				else:
					agency_dict[agency_abrv][agency_comp][dc_id]={'warnings':warnings,'errors':errors}
			else:
				agency_dict[agency_abrv][agency_comp]={dc_id:{'warnings':warnings,'errors':errors}}
		else:
			agency_dict[agency_abrv]={agency_comp:{dc_id:{'warnings':warnings,'errors':errors}}}

# Dictionary comprehension takes agency_dcit and creates a single layer key/value pair
# the key is a tuple of ageny_dict's four keys
new_dict = {(k1,k2,k3,k4):v4 \
			for k1,v1 in agency_dict.items()\
			for k2,v2 in agency_dict[k1].items()\
			for k3,v3 in agency_dict[k1][k2].items()\
			for k4,v4 in agency_dict[k1][k2][k3].items()\
			}

# create a multiindex pandas data frame from the tuple keys in new_dit
df = pd.DataFrame([new_dict[i] for i in sorted(new_dict)],
                  index=pd.MultiIndex.from_tuples([i for i in sorted(new_dict.keys())],names=['Agency','Component','DCID','Error Message']))

# this is a messy work around.  The csv.DictReader was reading the first line (headers) and applying the error logic to it
# this resulted in two rows being added to the error message output and erroneous indexes in the dataframe
# instead of creating a new iterator object and updating the row calls, I just filtered out the erroneous rows on the 'Agency"
# index column 
df = df.iloc[df.index.get_level_values('Agency') != 'agency abbreviation']

# get the path the project is stored in
path = os.getcwd()
agency_files = os.path.join(path,'Agency_Folder')
# find a unique list of values in the 'Agency' index column
unique_agencies = list(set(df.index.get_level_values('Agency')))

# make directory
if not(os.path.exists(agency_files)):
	os.mkdir(agency_files)
else:
	pass

# iterate through unique_agencies, assigning each unique one to a dataframe, saving that to a folder in my directory as a csv
for i in unique_agencies:	

	new_df = df.iloc[df.index.get_level_values('Agency') == i]

	# because of csv.DictReader applied the error message logic to the header row it created 19 empty columns in the data frame
	new_df.dropna(inplace=True,axis=1,how='all')

	new_df.to_csv(os.path.join(path,'Agency_Files/{} DCOI Validation.csv'.format(i)),index_label=['Agency','Component','DCID','Error Message'])