import datetime
import json
import time
import urllib.request
from configparser import ConfigParser
from statistics import mean

import aqi
import psycopg2
import sds011


# https://tutswiki.com/read-write-config-files-in-python/
def create_config() -> None:
    config_object = ConfigParser()
    config_object["Database"] = {
        "host_ip":  '192.168.1.1',
        "port": '5432',
        "database": 'testbed',
        "user": '',
        "password": ''
    }
    config_object["Sensor"] = {
        "port": 'COM4',
        "baudrate": 9600,
        "sensor_id": '1'
    }

    with open('config.ini', 'w') as conf:
        config_object.write(conf)


def check_purple_aq(sensor_list: str = ['17621', '17663']) -> dict:
    #https://www.purpleair.com/json?show=123456
    #Sensors 17621 / 17663
    pm2_5 = []
    aqi2_5 = []
    pm10 = []
    aqi10 = []
    temp = []
    humidity = []
    s_nfo = dict()
    if not isinstance(sensor_list, list):  #handle if single item in non-list is entered
        sensor = str(sensor_list)
        sensor_list = [sensor]
    for sensor in sensor_list:
        if len(sensor_list) > 1:   #Give a second between requests to avoid getting throttled by API
            time.sleep(1)
        with urllib.request.urlopen("https://www.purpleair.com/json?show={0}".format(sensor)) as url:
            data = json.loads(url.read().decode())
            try:
                pm2_5.append((float(data['results'][1]['pm2_5_atm'])+float(data['results'][0]['pm2_5_atm']))/2)
                aqi2_5.append(int(aqi.to_iaqi(aqi.POLLUTANT_PM25, str(pm2_5[-1]))))
                pm10.append((float(data['results'][1]['pm10_0_atm'])+float(data['results'][0]['pm10_0_atm']))/2)
                aqi10.append(int(aqi.to_iaqi(aqi.POLLUTANT_PM10, str(pm10[-1]))))
                humidity.append(int(data['results'][0]['humidity']))
                temp.append(int(data['results'][0]['temp_f']))
            except Exception as e:
                print('Error from Purple Air sensor:', e)
                s_nfo['pm2_5'] = 'NULL'
                s_nfo['aqi2_5'] = 'NULL'
                s_nfo['pm10'] = 'NULL'
                s_nfo['aqi10'] = 'NULL'
                s_nfo['humidity'] = 'NULL'
                s_nfo['temp'] = 'NULL'
                return s_nfo
    #print(round(mean(pm2_5), 2), round(mean(aqi2_5)), round(mean(pm10), 2), round(mean(aqi10)), round(mean(humidity)), round(mean(temp)))
    s_nfo['pm2_5'] = round(mean(pm2_5), 2)
    s_nfo['aqi2_5'] = round(mean(aqi2_5))
    s_nfo['pm10'] = round(mean(pm10), 2)
    s_nfo['aqi10'] = round(mean(aqi10))
    s_nfo['humidity'] = round(mean(humidity))
    s_nfo['temp'] = round(mean(temp))
    return s_nfo

##make it work
def read_config():
    config_object = ConfigParser()
    config_object.read("config.ini")
    return config_object


##TODO Make this work with AWS


def read_sensor(sensor, wait_time: int, readings: int) -> [float, float]:
    if wait_time < 1:
        wait_time = 5
    if readings < 1:
        return None
    pm_2_5, pm_10 = sensor.query()
    avg_2_5 = pm_2_5 / readings
    avg_10 = pm_10 / readings
    for read in range(readings):
        time.sleep(wait_time)
        pm_2_5, pm_10 = sensor.query()
        avg_2_5 += (pm_2_5/readings)
        avg_10 += (pm_10/readings)
    return [round(avg_2_5, 1), round(avg_10, 1)]


# Function to turn off sensor to avoid burning out laser
def stop_sensor():
    config = read_config()
    sensor_config = config['Sensor']
    try:
        sensor = sds011.SDS011(sensor_config['port'], baudrate=sensor_config['baudrate'], use_query_mode=True)
    except Exception as e:
        print('Could not connect to sensor.')
        print(e)
        return None
    print('Shutdown sensor if still running')
    sensor.sleep(sleep=True)
    return None


def start_tracking():
    error_cnt = 0
    old_error_cnt = 0
    config = read_config()
    database_config = config['Database']
    sensor_config = config['Sensor']
    try:
        conn = psycopg2.connect(
            host=database_config['host_ip'],
            port=database_config['port'],
            database=database_config['database'],
            user=database_config['user'],
            password=database_config['password'])
    except Exception as e:
        print('Database could not be connected to:')
        print(e)
        return None
    cur = conn.cursor()
    try:
        sensor = sds011.SDS011(sensor_config['port'], baudrate=sensor_config['baudrate'], use_query_mode=True)
    except Exception as e:
        print('Could not connect to sensor.')
        print(e)
        return None
    # print(conn.execute("Select * from test_table"))
    n = 0
    stop_run, run_wait_time, samples, wait_per_sample = check_controls(cur, int(sensor_config['sensor_id']))
    while True:    # Currently infinite loop #Set sensor_controls.stop_readings to True to stop
        n += 1
        print('Waking up sensor')
        sensor.sleep(sleep=False)
        time.sleep(30)
        print('Taking reads')
        pm_2_5, pm_10 = read_sensor(sensor, wait_per_sample, samples)
        aqi_2_5 = aqi.to_iaqi(aqi.POLLUTANT_PM25, str(pm_2_5))
        aqi_10 = aqi.to_iaqi(aqi.POLLUTANT_PM10, str(pm_10))
        print('Get PurpleAir data')
        try:
            s_nfo = check_purple_aq()
        except Exception as e:
            errorlog=open("error.log","a")
            print('Check purple: {:%Y-%m-%d %H:%M:%S}: {}'.format(datetime.datetime.now(), str(e)),file=errorlog)
            errorlog.close()
            error_cnt+=1
        print('Loop '+str(n)+':', pm_2_5, pm_10, aqi_2_5, aqi_10)
        print('Purple air:', str(s_nfo['aqi2_5']), str(s_nfo['aqi10']), str(s_nfo['humidity']), str(s_nfo['temp']))
        now = datetime.datetime.now()
        # print("Current readings: ('{0}', {1}, {2}, {3}, {4})".format(str(now), str(pm_2_5), str(pm_10), str(aqi_2_5), str(aqi_10)))
        try:
            cur.execute("INSERT INTO testbed.public.test_table (timestamp, pm_2_5, pm_10, aqi_2_5, aqi_10, purple_aqi_2_5, purple_aqi_10, "
                    "humidity, temperature) values ('{0}',{1},{2},{3},{4},{5},{6},{7},{8})".format(str(now),
                    str(pm_2_5), str(pm_10), str(aqi_2_5), str(aqi_10), str(s_nfo['aqi2_5']), str(s_nfo['aqi10']),
                    str(s_nfo['humidity']), str(s_nfo['temp'])))
        except Exception as e:
            errorlog=open("error.log","a")
            print('Save readings: {:%Y-%m-%d %H:%M:%S}: {}'.format(datetime.datetime.now(), str(e)),file=errorlog)
            errorlog.close()
            error_cnt+=1
        conn.commit()
        sensor.sleep(sleep=True)
        for minute in range(0, run_wait_time):
            try:
                stop_run, run_wait_time, samples, wait_per_sample = check_controls(cur, int(sensor_config['sensor_id']))
            except Exception as e:
                errorlog=open("error.log","a")
                print('Check sensor control: {:%Y-%m-%d %H:%M:%S}: {}'.format(datetime.datetime.now(), str(e)),file=errorlog)
                errorlog.close()
                error_cnt+=1
            if stop_run:
                break
            time_to_run = run_wait_time - minute
            if time_to_run <= 0:
                break
            print("Time until next run: {0} minute(s)".format(time_to_run)) #todo fix (s) for minutes
            # print("Time until next run: {0} minute(s)".format(time_to_run), end='\r')
            time.sleep(60)
        if error_cnt>30:
            stop_run=True
        if old_error_cnt == error_cnt:   #check if errors are increasing with each cycle
            error_cnt = 0
            old_error_cnt = 0
        else:  #error for this cycle
            old_error_cnt=error_cnt
        if stop_run:
            break
        print("Starting next run")
    if stop_run and sensor_config['sensor_id']:
        try:
            cur.execute("UPDATE testbed.public.sensor_controls SET stop_readings = FALSE where sensor_controls.sensor = {}".format(sensor_config['sensor_id']))
            conn.commit()
        except Exception as e:
            errorlog=open("error.log","a")
            print('Update sensor control: {:%Y-%m-%d %H:%M:%S}: {}'.format(datetime.datetime.now(), str(e)),file=errorlog)
            errorlog.close()
            error_cnt+=1
    print("Shutting down sensor and DB connection.")
    conn.close()
    sensor.sleep(sleep=True)
    return None

# Just used for testing
def test_hold():
    config = read_config()
    database_config = config['Database']
    sensor_config = config['Sensor']
    try:
        conn = psycopg2.connect(
            host=database_config['host_ip'],
            port=database_config['port'],
            database=database_config['database'],
            user=database_config['user'],
            password=database_config['password'])
    except Exception as e:
        print('Database could not be connected to:')
        print(e)
        return None
    cur = conn.cursor()
    # cur.execute("select ctrl.stop_readings from sensor_controls as ctrl where ctrl.sensor = {0}".format(str(sensor_config.sensor_id)))
    # cur.execute("select ctrl.stop_readings from sensor_controls as ctrl where ctrl.sensor = 1")
    # row = cur.fetchone()
    stop_run, wait_time, samples, wait_per_sample = check_controls(cur, 2)
    if stop_run:
        print("Ending Run")
        return None
    print('Continuing run', wait_time, samples, wait_per_sample)
    conn.close()
    return None


def check_controls(cursor, sensor_id: int = 0) -> (bool, int, float):
    stop_run = False
    wait_per_sample, wait_time, samples = [0] * 3 # Declare variables in case they come back as null
    if not cursor:
        return None
    cursor.execute("select ctrl.stop_readings, ctrl.samples_per_read, ctrl.wait_btw_samples, ctrl.wait_btw_read from testbed.public.sensor_controls as ctrl where ctrl.sensor = {0}".format(str(sensor_id)))
    row = cursor.fetchone()
    if row:
        stop_run = row[0]
        samples = row[1]
        wait_per_sample = row[2]
        wait_time = row[3]
    if not stop_run:
        stop_run = False
    if not wait_time or wait_time < 1:
        wait_time = 15
    if not samples or samples < 1:
        samples = 5
    if not wait_per_sample or wait_per_sample < 1:
        wait_per_sample = 6
    return stop_run, wait_time, samples, wait_per_sample


def main():
    print('Starting process...')
    start_tracking()
    # test_hold()
    # create_config()
    return None


if __name__ == '__main__':
    main()
