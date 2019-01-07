import time

import paramiko
from getpass import getpass

install_script_url = "http://cdn.ispsystem.com/install.sh"


class Server:
    installed_panels = []
    mysql_password = ""

    def __init__(self, ip, password):
        self.ip = ip
        self.password = password
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(ip, username="root", password=password)

    def exec(self, command):
        stdin, stdout, stderr = self.ssh.exec_command(command)
        _out = ""
        for line in stdout:
            _out = _out + line
            print(line.strip("\n"))
        print("---------------------------------------")
        return _out

    def mgrctl_exec(self, manager, params):
        return self.exec("/usr/local/mgr5/sbin/mgrctl -m " + manager + " " + params)

    def disable_selinux(self):
        print("Проверяем SElinux.. ")
        if self.exec("getenforce").strip('\n') == "Enforcing":
            print("SElinux включен, необходимо перезагрузить сервер и запустить скрипт повторно")
            self.exec("echo \"SELINUX=disabled\" > /etc/selinux/config")
            if input("Перезагрузить сервер? (y/n)") == 'y':
                self.exec("reboot")
                exit(0)
            else:
                print("Наверное нет")
                exit(0)

    def install_billmanager(self, edition):
        product = 5577
        mgr = "billmgr"
        if edition.lower() != "advanced":
            print("Эта версия ещё не поддерживается")
            exit(0)

        manager_lic_key = input(
            "Введите ключ лицензии, если необходима ручная активация по ключу (например, если сервер находится за NAT), "
            "в противном случае оставьте поле пустым")
        self.disable_selinux()
        print("Устанавливаем wget и скачиваем скрипт... ")
        self.exec("yum -y install wget && wget http://cdn.ispsystem.com/install.sh")
        print("Запускаем скрипт установки... ")
        self.exec("sh install.sh --release beta billmanager-" + edition.lower())

        print("Получаем лицензию для установленной панели... ")
        lic_info = self.exec("/usr/local/mgr5/sbin/licctl info billmgr")
        lic_id = lic_info.split("ID: ")[1].split('\n')[0]
        if lic_id == "0":
            print("Нет лицензии")

        if manager_lic_key != "":
            print("Активируем по ключу...")
            self.exec("/usr/local/mgr5/sbin/licctl fetch " + mgr + " " + manager_lic_key)
            time.sleep(5)
            lic_info = self.exec("/usr/local/mgr5/sbin/licctl info " + mgr)
            lic_id = lic_info.split("\n")[0]
            if lic_id == "ID: 0":
                print("Всё ещё нет лицензии, получаем триал")
        else:
            email = input("Введите ваш e-mail: ")
            out = self.mgrctl_exec("billmgr",
                                   "licenseorder agreement=on clicked_button=next email=" + email + " period=1 product=" + str(
                                       product) + " " +
                                   "sok=ok "
                                   "type=trial out=text | grep -v \"password\"")

            if "after_payment_info=" in out:  # если такого email`а не было в нашем биллинге
                manager_lic_key = input("На указанный e-mail было отправлено письмо с ключом, введите его: ")
                self.exec("/usr/local/mgr5/sbin/licctl fetch billmgr " + manager_lic_key)
            else:  # если уже есть
                print("На my.ispsystem.com уже существует такой пользователь")
                password = getpass("Введите ваш пароль от my.ispsystem.com для данного пользователя: ")
                self.mgrctl_exec("billmgr",
                                 "licenseorder email=" + email + " agreement=on product=" + str(
                                     product) + " period=1 password=" + password + " type=trial | grep -v \"password\"")
                manager_lic_key = input(
                    "На указанный e-mail было отправлено письмо с активационным ключом, введите его: ")
                self.exec("/usr/local/mgr5/sbin/licctl fetch billmgr " + manager_lic_key)

        print("BILLmanager установлен")

    def get_installed_panels(self):
        for name in self.exec("/usr/local/mgr5/sbin/mgrctl mgr").split("\n")[0:-1]:
            self.installed_panels.append(name.split("=")[1])

billmgr_ip = "192.168.1.7"
billmgr_pass = "qweasdzxc"
billmgr_version = "advanced"

billmgr = Server(billmgr_ip, billmgr_pass)

billmgr.install_billmanager(billmgr_version)
billmgr.get_installed_panels()
print(billmgr.installed_panels)