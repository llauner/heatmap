# icg2geojson.py
# Author: Tilen Ceglar
# Contributor: Ludovic Lauyner
# January 2020

import os
import datetime
import argparse     as ap
import numpy as np
import geojson as gjson
import time
# from scipy.interpolate import *

DT = 60 # Time averaging factor

def read_igc(input):
    """reads .igc file and returns in order:
            - gps fix line data
            - epoch timestamps
            - latitudes
            - longitudes
            - pressure altitudes
            - task points
            - raw_data
    """
    raw_data = []
    time = []
    lat = []
    lon = []
    palt = []
    task =[]
    tdata = []
    engine_noise_levels = []
    # ENL if applicable
    is_enl_present = False
    enl_index_start = None
    enl_index_stop = None
    
    for line in open(input):
        if line.startswith(('HFDTE')):
            day, month, year = line[5:7], line[7:9], line[9:11]
        if line.startswith('I') and line.find("ENL")>-1:                   # Look for ENL location in B message if applicable
            enl_index = line.index("ENL")
            is_enl_present = True
            enl_index_start = int(line[enl_index-4:enl_index-2])
            enl_index_stop = int(line[enl_index-2:enl_index])
        if line.startswith(('B')):
            raw_data.append(line.replace('\n',''))
            HHMMSS, DDMMMMMN, DDDMMMMME, PPPPP = int(line[1:7]), int(line[7:14]), int(line[15:23]), float(line[25:30])

            t_h = float(line[1:3])
            t_m = float(line[3:5])
            t_s = float(line[5:7])
            # time_= (t_h*60+t_m)*60+t_s
            timest = '{0}-{1}-20{2} {3}:{4}:{5}'.format(day,month,year,int(t_h),int(t_m),int(t_s))

            epoch = int(datetime.datetime(2000+int(year), int(month), int(day), int(t_h), int(t_m), int(t_s)).timestamp())

            enl = int(line[enl_index_start:enl_index_stop+1]) if is_enl_present else None

            # Add point into dataset
            is_point_valid = True 
            if not (enl is None) and  enl >= 60:   # Check for ENL level
                is_point_valid = False

            p=1
            g=1
            if line[14]=='S':
                p=-1
            if line[23]=='W':
                g=-1
            lat_ = (float(line[7:9])+(float(line[9:11])+ float(line[11:14])/1000)/60)*p
            lon_ = (float(line[15:18])+(float(line[18:20])+ float(line[20:23])/1000)/60)*g

            if is_point_valid:
                time.append(epoch)
                lat.append(lat_)
                lon.append(lon_)
                palt.append(PPPPP)
                tdata.append([timest, lat_, lon_, PPPPP])
                engine_noise_levels.append(enl)

        # if line.startswith('C'):
        #     if i!=0:
        #         task.append([float(line[9:12])+(float(line[12:14])+ float(line[14:17])/1000)/60,
        #                      float(line[1:3])+(float(line[3:5])+ float(line[5:8])/1000)/60])
        #     i+=1

    return tdata, time, np.asarray(lat), np.asarray(lon), np.asarray(palt), task, np.asarray(engine_noise_levels)

def average_t(x,dx):
    """time averaging over DT"""
    y = np.mean(np.asarray(x[:(len(x)//dx)*dx]).reshape(-1,dx), axis=1)
    return y

#Grabs directory and outname
parser = ap.ArgumentParser()
parser.add_argument('dir',          help='Path to bulk .igc files'  )
parser.add_argument('output',       help='Geojson file name'        )
arguments = parser.parse_args()

dir = arguments.dir
output = arguments.output

# Create output file name by adding date and time as a suffix
output = arguments.output
now = epoch_time = int(time.time())
dir_name = os.path.dirname(output)
file_name = os.path.basename(output)
output = dir_name + "\\" + str(now) + "_" + file_name

#Read .igc files names in a directory
files = []
for file in os.listdir("{}".format(dir)):
    if file.endswith(".igc"):
        files.append(file)

fix_big = []
w_big = []

#Collect all flights and average them over DT
for file in files:
    tuple_igc = read_igc("{0}/{1}".format(dir, file))

    timestamp_average = average_t(tuple_igc[1],DT)
    latitude_a = average_t(tuple_igc[2],DT)
    longitude_a = average_t(tuple_igc[3],DT)
    engine_noise_levels = tuple_igc[6]

    # Compute average vario
    altitude_average = average_t(tuple_igc[4],DT)
    try:
        vario_average = np.gradient(altitude_average,timestamp_average)
    except:
        # TODO: No idea why the aboce function fails in some cases...will have to investigate...
        pass

    
    for timestamp, vario, lat, lon, alt, enl in zip(timestamp_average,vario_average,latitude_a,longitude_a,altitude_average, engine_noise_levels):
        if vario>=0:
            fix = np.stack((int(timestamp), lat,lon,alt, enl))
            fix_big.append(fix)
            w_big.append(vario)

#Create gjson points
features = []
for point, m in zip(fix_big,w_big):
    json_point=gjson.Point((point[2],point[1],int(point[3])))
    timestamp = point[0]
    enl = point[4]
    features.append(gjson.Feature(geometry=json_point, properties={"vario": round(m,2), "enl": enl, "time": timestamp}))

feature_collection = gjson.FeatureCollection(features)

#Write output
with open('{}.geojson'.format(output), 'w') as f:
    gjson.dump(feature_collection, f)
