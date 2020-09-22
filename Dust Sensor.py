import serial
import sds011
import aqi
import time
import psycopg2
import datetime
from configparser import ConfigParser

# https://tutswiki.com/read-write-config-files-in-python/
def create_config() -> None:
    config_object = ConfigParser()
    config_object["Database"] = {
        "host_ip":  '192.168.1.56',
        "port": '5432',
        "database": 'testbed',
        "user": 'postgres',
        "password": ''
    }
    config_object["Sensor"] = {
        "port": 'COM4',
        "baudrate": 9600
    }
    with open('config.ini', 'w') as conf:
        config_object.write(conf)


def read_config():
    config_object = ConfigParser()
    config_object.read("config.ini")
    return config_object

def readSensor(sensor, wait_time: int, readings: int) -> [float, float]:
    if wait_time < 1:
        wait_time = 5
    if readings < 1:
        return None
    avg_2_5 = 0
    avg_10 = 0
    pm_2_5, pm_10 = sensor.query()
    avg_2_5 = pm_2_5 / readings
    avg_10 = pm_10 / readings
    for read in range(readings):
        time.sleep(wait_time)
        pm_2_5, pm_10 = sensor.query()
        avg_2_5 = avg_2_5 + (pm_2_5/readings)
        avg_10 = avg_10 + (pm_10/readings)
    return [round(avg_2_5, 1), round(avg_10, 1)]


def start_tracking():
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
    except:
        print('Database could not be connected to.')
        return None
    cur = conn.cursor()
    try:
        sensor = sds011.SDS011(sensor_config['port'], baudrate=sensor_config['baudrate'], use_query_mode=True)
    except:
        print('Could not connect to sensor.')
        return None
    # print(conn.execute("Select * from test_table"))
    n = 0
    while True:
        n += 1
        print('Waking up sensor')
        sensor.sleep(sleep=False)
        time.sleep(60)
        print('Taking reads')
        pm_2_5, pm_10 = readSensor(sensor, 6, 5)
        aqi_2_5 = aqi.to_iaqi(aqi.POLLUTANT_PM25, str(pm_2_5))
        aqi_10 = aqi.to_iaqi(aqi.POLLUTANT_PM10, str(pm_10))
        print('Loop '+str(n)+':', pm_2_5, pm_10, aqi_2_5, aqi_10)
        now = datetime.datetime.now()
        print(now)
        print("This is now ('{0}',{1},{2},{3},{4})".format(str(now), str(pm_2_5), str(pm_10), str(aqi_2_5), str(aqi_10)))
        cur.execute("INSERT INTO test_table values ('{0}',{1},{2},{3},{4})".format(str(now), str(pm_2_5), str(pm_10), str(aqi_2_5), str(aqi_10)))
        conn.commit()
        sensor.sleep(sleep=True)
        print('Cooldown')
        wait_time = 10 #wait time between runs in minutes.
        for minute in range(0, wait_time):
            print("Time until next run:{0} minute(s)".format(str(wait_time-minute)), end='\r')
            time.sleep(60)
        print("Starting next run")

    conn.close()
    sensor.sleep(sleep=True)


def main():
    print('Starting process...')
    start_tracking()
    # create_config()
    return None


if __name__ == '__main__':
    main()

# ser = serial.Serial('COM4', 9600, timeout=0,parity=serial.PARITY_EVEN, rtscts=1)
# print(ser.name)         # check which port was really used
# print(ser.read(19))
# # ser.write(b'hello')     # write a string
# ser.close()           # close port
# serial.Serial('COM4',9600).close()
# sensor = sds011.SDS011('COM4', baudrate=9600, use_query_mode=True)
# print(sensor.query())
# sensor.sleep()
# sensor.sleep(30)
# sensor.sleep(sleep=False)
# sensor.sleep(30)
# time.sleep(30)
# for n in range(30):
#     sensor.sleep(sleep=True)
#     time.sleep(15)
#     print('45 Seconds')
#     time.sleep(15)
#     sensor.sleep(sleep=False)
#     time.sleep(15)
#     print("15 Seconds")
#     time.sleep(15)
#     pm_2_5, pm_10 = sensor.query()
#     aqi_2_5 = aqi.to_iaqi(aqi.POLLUTANT_PM25, str(pm_2_5))
#     aqi_10 = aqi.to_iaqi(aqi.POLLUTANT_PM10, str(pm_10))
#     print('Loop '+str(n)+':', pm_2_5, pm_10, aqi_2_5, aqi_10)
