# iot-azure

# list of library to install on raspberry pi5
apt list --upgradable
sudo apt upgrade
sudo apt install ca-certificates build-essential python3-serial git socket telnet curl nmap speedtest-cli  net-tools traceroute iputils-ping squeekboard sense-hat
sudo apt update

## to configure git
git config --global user.email "bara.emran@gmail.com"

git config --global user.name "bara Emran"

eval "$(ssh-agent -s)"

ssh-add ~/.ssh/id_rsa

cat ~/.ssh/id_rsa.pub

## to run the code
git clone git@github.com:BEmran/iot-azure.git
cd iot-azure/
python -m venv venv
source venv/bin/activate
pip install -r requierments.txt 
python azure-iot-example_thread.py 

## to enable the iot code to run at boot time
sudo cp iotapp.service /etc/systemd/system/iotapp.service
sudo systemctl daemon-reload
sudo systemctl enable iotapp.service
sudo systemctl start iotapp.service
journalctl -u iotapp.service -f
sudo reboot now


For the run_all_tests.sh: 
Create the default devices file (devices.txt)

In the same folder as the scripts:
nano devices.txt

Example content:
# Attendance devices in this site
192.168.1.50
192.168.1.51

# You can also use commas:
192.168.1.52, 192.168.1.53

Run using the default file
./run_all_tests.sh -a
