import random
import time

import paramiko
from getpass import getpass

install_script_url = "http://cdn.ispsystem.com/install.sh"


def generate_password():
    pas = ''
    for x in range(10):  # Количество символов (16)
        pas = pas + random.choice(list('1234567890abcdefghigklmnopqrstuvyxwzABCDEFGHIGKLMNOPQRSTUVYXWZ'))
    return pas


class Server:
    installed_panels = []
    mysql_password = ""
    user_email = ""
    user_password = ""

    def install_panel(self, manager):
        self.disable_selinux()
        print("Устанавливаем wget и скачиваем скрипт... ")
        self.exec("yum -y install wget && wget http://cdn.ispsystem.com/install.sh -O install.sh")
        print("Устанавливаем панель... ")
        self.exec("sh install.sh --release beta " + manager)

    def log(self, line):
        #        print(line.strip("\n"))
        pass

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
            self.log(line)
        self.log("---------------------------------------")
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
        if "billmgr" in self.get_installed_panels():
            print("BILLmanager уже установлен")
            return
        product = 5577
        mgr = "billmgr"
        if edition.lower() != "advanced":
            print("Эта версия ещё не поддерживается")
            exit(0)
        self.install_panel("billmanager-" + edition.lower())
        print("Получаем лицензию для установленной панели... ")
        lic_info = self.exec("/usr/local/mgr5/sbin/licctl info billmgr")
        lic_id = lic_info.split("ID: ")[1].split('\n')[0]
        if lic_id == "0":
            print(" Автоматически активировать не удалось")

        manager_lic_key = input(
            "Введите ключ лицензии, если у вас имеется лицензия на панель: ")

        if manager_lic_key != "":
            print("Активируем по ключу...")
            self.exec("/usr/local/mgr5/sbin/licctl fetch " + mgr + " " + manager_lic_key)
            time.sleep(5)
            lic_info = self.exec("/usr/local/mgr5/sbin/licctl info " + mgr)
            lic_id = lic_info.split("\n")[0]
            if lic_id == "ID: 0":
                print("Ключ не подошёл, ой!")
                exit(1)
        else:
            if self.user_email == "":
                self.user_email = input("Введите ваш e-mail: ")
            out = self.mgrctl_exec("billmgr",
                                   "licenseorder agreement=on clicked_button=next email=" + self.user_email + " period=1 product=" + str(
                                       product) + " " +
                                   "sok=ok "
                                   "type=trial out=text | grep -v \"password\"")

            if "after_payment_info=" in out:  # если такого email`а не было в нашем биллинге
                manager_lic_key = input("На e-mail " + self.user_email + " было отправлено письмо с ключом, введите его: ")
                self.exec("/usr/local/mgr5/sbin/licctl fetch billmgr " + manager_lic_key)
            else:  # если уже есть
                print("На my.ispsystem.com уже существует пользователь " + self.user_email)
                if self.user_password == "":
                    self.user_password = getpass("Введите ваш пароль от my.ispsystem.com для данного пользователя: ")
                self.mgrctl_exec("billmgr",
                                 "licenseorder email=" + self.user_email + " agreement=on product=" + str(
                                     product) + " period=1 password=" + self.user_password + " type=trial | grep -v \"password\"")
                manager_lic_key = input(
                    "На указанный e-mail было отправлено письмо с активационным ключом, введите его: ")
                self.exec("/usr/local/mgr5/sbin/licctl fetch billmgr " + manager_lic_key)

        print("BILLmanager установлен")

    def install_ipmanager(self):
        if "ipmgr" in self.get_installed_panels():
            print("IPmanager уже установлен")
        else:
            self.install_panel("ipmanager")
        if len(self.mgrctl_exec("ipmgr", "user").split("\n")) > 2:
            print("В панели уже существуют пользователи, автоматическая конфигурация невозможна")
            return

        self.ipmanager_user_password = generate_password()
        self.mgrctl_exec("ipmgr", "user.edit passwd=" + self.ipmanager_user_password + " confirm=" + self.ipmanager_user_password +
                         " sok=ok name=billmgr")
        # TODO



    def billmanager_preconfigure(self):
        if self.mysql_exec("billmgr", "select * from project;") != "":
            print("Этот BILLmanager уже сконфигурирован")
            return
        print("Начинаем преконфигурацию BILLmanager")
        lang = "ru"
        country_id = ""
        currency_id = ""
        profiletype = ""
        billurl = "https://" + self.exec("/usr/local/mgr5/sbin/ihttpd").split(" ")[1].split("\n")[0]

        while country_id == "":
            country = input("Введите код страны в формате ISO2: ").lower()
            country_id = self.mysql_exec("billmgr", "select id from country where iso2='" + country + "';").strip("\n")
            if country_id == "":
                print("Некорректный код страны")

        while profiletype == "":
            profiletype = input("Выберите юридический статус: \n"
                                "1 - Физическое лицо\n"
                                "2 - Юридическое лицо\n"
                                "3 - Индивидуальный предприниматель\n"
                                "Выбор (1-3): ")
            try:
                profiletype = int(profiletype)
                if type(profiletype) is not int or profiletype < 1 or profiletype > 3:
                    profiletype = ""
                    raise Exception("Некорректный тип")
                break
            except:
                profiletype = ""

        provider_name = input("Наименование провайдера: ")

        while currency_id == "":
            currency = input("Код валюты в формате ISO: ").upper()
            currency_id = self.mysql_exec("billmgr", "select id from currency where ISO='" + currency + "';").strip(
                "\n")
            if currency_id == "":
                print("Некорректный код валюты")

        request = "initialsettings.project" + " profiletype=" + str(
            profiletype) + " project_billurl=" + billurl + " currency=" + str(currency_id) + " country=" + str(
            country_id) + " project_name='" + provider_name + "' clicked_button=finish sok=ok"

        out = self.mgrctl_exec("billmgr", request)

        if out.split(" ")[0] != "ERROR":
            print("Настройка завершена")
        else:
            print(out)

    def get_installed_panels(self):
        self.installed_panels = []
        for name in self.exec("/usr/local/mgr5/sbin/mgrctl mgr").split("\n")[0:-1]:
            self.installed_panels.append(name.split("=")[1])
        return self.installed_panels

    def get_mysql_password(self):
        file = self.exec("cat /usr/local/mgr5/etc/my.cnf")
        self.mysql_password = file.split("password = ")[1].strip("\n")
        return self.mysql_password

    def mysql_exec(self, db, command):
        if self.mysql_password == "":
            self.get_mysql_password()
        sql = "mysql --skip-column-names -ucoremgr -p" + self.mysql_password + " -e \"" + command + "\" " + db + "|cat -"
        return self.exec(sql)


billmgr_ip = "172.31.223.23"
billmgr_pass = "H6n6J6j6"
billmgr_version = "advanced"

billmgr = Server(billmgr_ip, billmgr_pass)

# billmgr.install_billmanager("advanced")
# billmgr.install_ipmanager()
# print(billmgr.get_installed_panels())

billmgr.install_ipmanager()
