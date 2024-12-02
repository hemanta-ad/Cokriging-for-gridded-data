import arcpy
import os
import datetime
from arcpy.sa import *

arcpy.env.overwriteOutput = True

# Check out the ArcGIS Geostatistical Analyst extension license
arcpy.CheckOutExtension("GeoStats")

# Get parameters
workspace = arcpy.GetParameterAsText(0)
fc = arcpy.GetParameterAsText(1)  # Feature Layer
dem = arcpy.GetParameterAsText(2)
xml_folder = arcpy.GetParameterAsText(3)
clpbnd = arcpy.GetParameterAsText(4)
gridres = arcpy.GetParameterAsText(5)
ncfile = arcpy.GetParameterAsText(6)

# Print parameters to debug
arcpy.AddMessage("Parameters:")
arcpy.AddMessage("Workspace: {}".format(workspace))
arcpy.AddMessage("CSV File: {}".format(fc))
arcpy.AddMessage("DEM: {}".format(dem))
arcpy.AddMessage("XML Folder: {}".format(xml_folder))
arcpy.AddMessage("Clipping Boundary: {}".format(clpbnd))
arcpy.AddMessage("Grid Resolution: {}".format(gridres))
arcpy.AddMessage("NetCDF File: {}".format(ncfile))

# Set environment workspace
arcpy.env.workspace = workspace

# Check if workspace is valid
if not workspace or not os.path.isdir(workspace):
    arcpy.AddError("Workspace is not provided or is invalid.")
    raise ValueError("Workspace is not provided or is invalid.")

# Create working temp folders
try:
    tif_folder = os.path.join(workspace, "tif")
    tmp_folder = os.path.join(tif_folder, "tmp")

    # Print folder paths for debugging
    arcpy.AddMessage("tif_folder path: {}".format(tif_folder))
    arcpy.AddMessage("tmp_folder path: {}".format(tmp_folder))

    arcpy.AddMessage("Creating folder: {}".format(tif_folder))
    arcpy.CreateFolder_management(workspace, "tif")

    arcpy.AddMessage("Creating folder: {}".format(tmp_folder))
    arcpy.CreateFolder_management(tif_folder, "tmp")
except arcpy.ExecuteError:
    arcpy.AddError("ArcPy ExecuteError: " + arcpy.GetMessages(2))
    raise
except Exception as e:
    arcpy.AddError("General Error: {}".format(e))
    raise

# Set local variables
tiffold = os.path.join(workspace, "tif")
tmpfold = os.path.join(tiffold, "tmp")

arcpy.env.extent = clpbnd

arcpy.CreateFileGDB_management(workspace, "tempsurface.gdb")
gdbloc = os.path.join(workspace, "tempsurface.gdb")

sr = arcpy.Describe(fc).spatialReference
arcpy.CreateRasterCatalog_management(gdbloc, "Temperature", sr, sr, "", "0", "0", "0", "MANAGED", "")
cat = os.path.join(gdbloc, "Temperature")

arcpy.CreateFileGDB_management(tmpfold, "temp.gdb")
fc1 = os.path.join(tmpfold, "temp.gdb", "fc1")

# Creating dem string (aspect variable removed)
str1 = "{} Elev; {};".format(fc, dem)

outLayer = os.path.join(workspace, "tmp", "tmp2out.tif")
calc = "calc"

# Print all fields to debug
all_fields = arcpy.ListFields(fc)
field_names = [field.name for field in all_fields]
arcpy.AddMessage("All fields in feature class: {}".format(field_names))

# Define a mapping from month names to month numbers
month_map = {
    "Jan": "January", "Feb": "February", "Mar": "March", "Apr": "April",
    "May": "May", "Jun": "June", "Jul": "July", "Aug": "August",
    "Sep": "September", "Oct": "October", "Nov": "November", "Dec": "December"
}

# Adjust the pattern to match your field names
fields = arcpy.ListFields(fc, "Jan_*")  # Adjust pattern as needed
arcpy.AddMessage("Processing fields: {}".format([field.name for field in fields]))

if not fields:
    arcpy.AddError("No fields matched the pattern.")
    raise ValueError("No fields matched the pattern.")

# Extract year, month, and day from the first field name for time settings
first_field_name = fields[0].name
parts = first_field_name.split("_")
month_str = parts[0]
day_str = parts[1]
year_str = parts[2]

year0 = year_str
month0 = month_map[month_str]
day0 = day_str

year1 = int(year_str)
month1 = int(list(month_map.keys())[list(month_map.values()).index(month0)])
day1 = int(day0)
monthdate = "{}{}{}".format(year0, str(month1).zfill(2), day0)

for field in fields:
    fldname = field.name
    fld = arcpy.da.TableToNumPyArray(fc, fldname, skip_nulls=True)
    tempsum = fld[fldname].sum()

    if int(tempsum) > 0:
        outgrid1 = os.path.join(tmpfold, "out{}.tif".format(field.name))
        outgrid0 = os.path.join(tmpfold, "T{}.tif".format(field.name))
        outgrid00 = os.path.join(tmpfold, "Tt{}.tif".format(field.name))
        outgrid = os.path.join(tiffold, "{}.tif".format(field.name))
        kriging = os.path.join(tmpfold, "cok_{}.tif".format(field.name))
        idw = os.path.join(tmpfold, "idw_{}.tif".format(field.name))
        fc1 = os.path.join(tmpfold, "temp.gdb", "tmp{}".format(field.name))
        inData = "{} {};{}".format(fc, field.name, str1)

        str2 = "processing {} date ......".format(field.name)
        arcpy.AddMessage(str2)

        # Assigning appropriate xml file for different months
        inLayer = os.path.join(xml_folder, "Kriging_2019_{}.xml".format(month0))
        arcpy.AddMessage("Using XML file: {}".format(inLayer))
        str3 = "Temperature Field = {}, Month = {}, xml file = Kriging_2019_{}.xml".format(field.name, month0, month0)
        arcpy.AddMessage(str3)

        # Check if the XML file exists
        if not os.path.exists(inLayer):
            arcpy.AddError("XML file does not exist: {}".format(inLayer))
            raise ValueError("XML file does not exist: {}".format(inLayer))

        # Execute CreateGeostatisticalLayer
        arcpy.GACreateGeostatisticalLayer_ga(inLayer, inData, outLayer)
        arcpy.GALayerToGrid_ga(outLayer, outgrid1, gridres, "1", "1")

        # Converting less than zero value with zero value
        outgrid10 = arcpy.Raster(outgrid1)
        temp2 = Con(outgrid10 < 0, 0, outgrid10)
        temp2.save(kriging)

        # Extract the elevation of interpolated raster grid at stations points
        ExtractValuesToPoints(fc, kriging, fc1, "NONE", "VALUE_ONLY")
        # Adding the calc field in temp fc1 layer
        arcpy.AddField_management(fc1, calc, "SHORT")
        # Execute CalculateField
        arcpy.CalculateField_management(fc1, calc, "!{}! - !RASTERVALU!".format(field.name), "PYTHON", "")

        # Additional line to be deleted later
        arcpy.gp.Idw_sa(fc1, calc, idw, gridres, "3", "VARIABLE 3", "")
        # Arithmetic addition of two rasters
        temp3 = Raster(kriging) + Raster(idw)
        temp3.save(outgrid00)

        # Converting less than zero value with zero value
        raster = arcpy.Raster(outgrid00)
        temp2 = Con(raster < 0, 0, raster)
        temp2.save(outgrid0)
        outExtractByMask = ExtractByMask(outgrid0, clpbnd)
        outExtractByMask.save(outgrid)
        arcpy.RasterToGeodatabase_conversion(outgrid, cat)

        # Deleting temporary layers
        arcpy.Delete_management(fc1)
        arcpy.Delete_management(kriging)
        arcpy.Delete_management(idw)
        arcpy.Delete_management(outgrid1)
        arcpy.Delete_management(outgrid0)
        arcpy.Delete_management(outgrid00)

    else:
        str9 = "processing {} date ......".format(field.name)
        arcpy.AddMessage(str9)
        zerotemp = os.path.join(workspace, "tif", "R{}.tif".format(monthdate))
        outgrid = os.path.join(tiffold, "{}.tif".format(field.name))
        temp4 = Raster(zerotemp) * 0
        temp4.save(outgrid)
        arcpy.RasterToGeodatabase_conversion(outgrid, cat)

arcpy.Delete_management(tmpfold)

# Inserting the date in the temperature catalog
field = ['Time']
arcpy.AddField_management(cat, "Time", "DATE")
cursor = arcpy.UpdateCursor(cat, field)
date = datetime.datetime(year1, month1, day1)  # start date
delta = datetime.timedelta(days=1)  # time offset

with arcpy.da.UpdateCursor(cat, field_names=('OBJECTID', 'Time',), sql_clause=('', 'ORDER BY OBJECTID')) as cur:
    for row in cur:
        row[1] = date
        date += delta
        cur.updateRow(row)

# Process: Raster to NetCDF
arcpy.AddMessage(cat)
arcpy.AddMessage(ncfile)
arcpy.RasterToNetCDF_md(cat, ncfile, "Temperature", "", "x", "y", "", "Time")

print("Finished")