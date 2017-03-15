# counter-redirecter

Сервер предназначен для осуществления прозрачного набора данных (точек) с детектора
с помощью дополнительного АЦП, подключенного к детектору.

counter-redirecter перенаправляет весь поток на сервер детектора. Если поступает 
команда о наборе точки, counter-redirecter также включает АЦП на набор и, по
завершении набора, записывает в метаданные точки (набранной основным способом)
указатель на соответствующий, набранный АЦП файл.

# Требования

- (Protobuf 3.2.0+)[https://github.com/google/protobuf/releases]
- Установленая программа [lan10-12pci_base](https://bitbucket.org/Kapot/lan10-12pci_base)

# Установка
1. Установить зависимости python

     pip3 install -r requrements.txt

2. Скомпилировать парсер

      cd configs && protoc rsb_event.proto  --python_out ../utils && cd ..

