if [ -e ./APCI ]; then
   echo "Clearing APCI"
   rm -rf ./APCI
fi
git clone https://github.com/accesio/APCI
cd APCI
make
sudo insmod apci.ko
sudo make install
echo "APCI installed, setting permissions"
sudo setfacl -m u:$USER:rw /dev/apci/*
echo "Building apcilib.so"
cd apcilib
gcc -shared -o apcilib.so -fPIC apcilib.c -lm -lpthread -O3