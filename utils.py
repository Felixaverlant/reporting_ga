import time
import os
import configparser

config = configparser.ConfigParser()
config.read('config.ini')

dir_path = os.path.dirname(os.path.realpath(__file__))
dir_folder = config['ConfProject']['folder']

def setup(dir_folder="reporting_images/"):
    directory = dir_folder+time.strftime("%d_%m_%Y")
    if not os.path.exists(directory):
        os.makedirs(directory)

def dir(dir_folder="reporting_images/"):
    return dir_path+"/"+dir_folder
