# iot-azure

#instruction
git config --global user.email "bara.emran@gmail.com"
git config --global user.name "bara Emran"
mkdir ws
cd ws

ssh-add ~/.ssh/id_rsa
cat ~/.ssh/id_rsa.pub

git clone git@github.com:BEmran/iot-azure.git


cd iot-azure/

python -m venv venv
source venv/bin/activate
pip install -r requierments.txt 
 
python azure-iot-example_thread.py 
