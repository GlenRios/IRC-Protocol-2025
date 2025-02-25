import socket
import threading
from User import User
from Channel import Channel
from cryptography.fernet import Fernet
from secret_key import SECRET_KEY
class IRCServer:
    def __init__(self, host='0.0.0.0', port=6667):
        self.host = host
        self.port = port
        self.clients= []
        self.nicknames= []
        self.channels= {'#General': Channel('General')}
        self.channel_modes = {
            'o': 'operator privileges (op/deop)',
            't': 'topic settable by channel operator only',
            'm': 'moderated channel',
        }
        
        self.user_modes = {
            'i': 'invisible',
        }
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        print(f"Servidor IRC escuchando en {self.host}:{self.port}")

        self.NUMERIC_REPLIES = {
            '001': 'Bienvenido al servidor IRC',
            '331': 'No hay topic establecido',
            '332': 'El topic es: %s',
            '353': 'Lista de usuarios en el canal',
            '366': 'Fin de la lista de usuarios',
            '401': 'Usuario/Canal no encontrado',
            '403': 'Canal no encontrado',
            '404': 'No puedes enviar mensajes a este canal',
            '421': 'Comando desconocido',
            '433': 'Nickname ya está en uso',
            '441': 'Usuario no está en el canal',
            '442': 'No estás en ese canal',
            '461': 'Faltan parámetros',
            '472': 'Modo desconocido',
            '482': 'No eres operador del canal',
            '502': "Un usuario solo puede cambiar sus propios modos"
        }

        self.cipher = Fernet(SECRET_KEY)  # Crea un objeto de cifrado


    def start(self):
        while True:
            client_socket, client_address = self.server_socket.accept()
            print(f"Nueva conexion desde {client_address}")
            client_handler = threading.Thread(target=self.handle_client, args=(client_socket,))
            client_handler.daemon = True
            client_handler.start()


    def handle_client(self, client_socket):
        """Maneja la conexión de un cliente."""
        # Mensaje de bienvenida con código 001
        welcome_message = ":001 :Bienvenido al servidor IRC local\r\n"
        encrypted_welcome = self.cipher.encrypt(welcome_message.encode())
        client_socket.sendall(encrypted_welcome)

        # Notificación de unión al canal General
        join_message = "Te has unido al canal #General\r\n"
        encrypted_join = self.cipher.encrypt(join_message.encode())
        client_socket.sendall(encrypted_join)

        while True:
            encrypted_data = client_socket.recv(4096)
            if not encrypted_data:
                break

            try:
                data = self.cipher.decrypt(encrypted_data).decode().strip()
                print(f"Recibido: {data}")
                response = self.process_command(client_socket, data)
                if response:
                    encrypted_response = self.cipher.encrypt((response + "\r\n").encode())
                    client_socket.sendall(encrypted_response)
            except Exception as e:
                print(f"Error al descifrar o procesar el mensaje: {e}")

        client = next((item for item in self.clients if item.socket == client_socket), None)
        if client: self.remove_client_from_channels(client)
        if client and client in self.clients: self.clients.remove(client)
        if client and client.nick in self.nicknames: self.nicknames.remove(client.nick)
        client_socket.close()
        print("Cliente desconectado")        


    def process_command(self, client_socket, data):
        parts = data.split(" ", 1)
        command = parts[0]
        argument = parts[1] if len(parts) > 1 else ""
        
        sender = next((item for item in self.clients if item.socket == client_socket), None)
        
        if command == "NICK":
            return self.change_nick(client_socket, argument)
        elif command == "MODE":
            return self.handle_mode(client_socket, argument)
        elif command == "USER":
            return "Usuario registrado."
        elif command == "JOIN":
            return self.join_channel(client_socket, argument)
        elif command == "PART":
            return self.part_channel(client_socket, argument)
        elif command == "PRIVMSG":
            return self.send_private_message(client_socket, argument)
        elif command == "NOTICE":
            return self.send_notice(client_socket, argument)
        elif command == "LIST":
            return self.list_channels()
        elif command == "NAMES":
            return self.list_users(argument)
        elif command == "WHOIS":
            return self.whois_user(client_socket, argument)
        elif command == "KICK":
            return self.kick_user(client_socket, argument)
        elif command == "TOPIC":
            return self.handle_topic(client_socket, argument)
        elif command == "QUIT":
            self.remove_client_from_channels(sender)
            self.clients.remove(sender)
            self.nicknames.remove(sender.nick)
            return f":{sender.nick} QUIT :Leaving"
            
        else:
            return f":421 {sender.nick} {command} :Unknown command"


    def add_nickname(self, nick):
        """Agrega un nickname a la lista de nicknames."""
        if nick not in self.nicknames:
            self.nicknames.append(nick)
            return True
        return False

    
    def remove_nickname(self, nick):
        """Elimina un nickname de la lista de nicknames."""
        if nick in self.nicknames:
            self.nicknames.remove(nick)
            return True
        return False

    
    def change_nick(self, client_socket, new_nick):
        client = next((item for item in self.clients if item.socket== client_socket), None)
        if new_nick in self.nicknames:
            return f':433 {new_nick} :{self.NUMERIC_REPLIES['433']}'
        
        elif client and client.nick == new_nick:
            return f':433 {new_nick} :{self.NUMERIC_REPLIES['433']}'
        
        elif client:
            old_nick= client.nick
            self.add_nickname(new_nick)
            self.remove_nickname(client.nick)

            for c in self.clients:
                if c.socket == client_socket:
                    c.nick = new_nick

            for _, channel in self.channels.items():
                for c in channel.users:
                    if c.socket == client_socket:
                        c.nick = new_nick
                for c in channel.operators:
                    if c.socket == client_socket:
                        c.nick = new_nick
   
            return f":{old_nick}! NICK {new_nick}"         
        else: 
            new_cli = User(client_socket, new_nick)
            self.clients.append(new_cli)  
            self.channels['#General'].add_user(new_cli)    
            return f":Usuario! NICK {new_nick}"


    def join_channel(self, client_socket, channel):
        client = next((item for item in self.clients if item.socket== client_socket), None)
        if channel not in self.channels:
            self.channels[channel]= Channel(channel)
            self.channels[channel].add_operator(client)
            return f"Te has unido al canal {channel}."
        if self.channels[channel].is_on_channel(client):
            return "El cliente ya está en el canal."
        self.channels[channel].add_user(client)
        self.channels[channel].broadcast(f":{client.nick}! JOIN {channel}", client)
        return f"Te has unido al canal {channel}."


    def part_channel(self, client_socket, channel):
        client = next((item for item in self.clients if item.socket== client_socket), None)
        if channel in self.channels and self.channels[channel].is_on_channel(client):
            self.channels[channel].remove_user(client)
            self.channels[channel].broadcast(f":{client.nick}! PART {channel}")
            return f"Saliste de {channel}."
        return f':442 :{self.NUMERIC_REPLIES['442']}'

    # Envia un mensaje ya sea a un usuario o a un canal
    def send_private_message(self, client_socket, argument):
        parts = argument.split(" ", 1)
        if len(parts) < 2:
            return f':sever 461 :{self.NUMERIC_REPLIES['461']}'
        target, message = parts
        sender = next((item for item in self.clients if item.socket== client_socket), None)
        c = [client.nick for client in self.clients]
        
        # Mensaje a un usuario
        if target in c:
            destination_sock = None
            for client in self.clients:
                if client.nick == target: 
                    destination_sock = client.socket
                    encrypted_message = self.cipher.encrypt((f":{sender.nick}! PRIVMSG {target} :{message}\r\n").encode())
                    destination_sock.sendall(encrypted_message)
            return f"Mensaje privado enviado a {target}: {message}"
        
        # Mensaje a un canal
        elif target in self.channels:
            if not self.channels[target].is_on_channel(sender):
                return f":442 :{self.NUMERIC_REPLIES['442']}"
            
            if self.channels[target].m and not self.channels[target].is_operator(sender):
                return f":482 :{self.NUMERIC_REPLIES['482']}"

            self.channels[target].broadcast(f":{sender.nick}! PRIVMSG {target} :{message}")
            return f"Mensaje enviado a {target}"

        # Si no es ni usuario ni canal, devolver mensaje de error
        return f':401 :{self.NUMERIC_REPLIES['401']}'

    # Envía un notice a un canal específico
    def send_notice(self, client_socket, argument):
        parts = argument.split(" ", 1)
        if len(parts) < 2:
            return f':461 :{self.NUMERIC_REPLIES['461']}'
        target, message = parts
        sender = next((item for item in self.clients if item.socket == client_socket), None)
        # Mensaje a un canal
        if target in self.channels:
            if not self.channels[target].is_on_channel(sender):
                return f':442 :{self.NUMERIC_REPLIES['442']}'
            
            if self.channels[target].m and not self.channels[target].is_operator(sender):
                return f":482 :{self.NUMERIC_REPLIES['482']}"
            
            self.channels[target].broadcast(f":{sender.nick} NOTICE {target} {message}")
            return f"Mensaje enviado a {target}"

        return  f':401 :{self.NUMERIC_REPLIES['401']}'


    def list_channels(self):
        channels= " ".join(self.channels.keys())
        return f"Lista de Canales: {channels}" 

    def list_users(self, channel):
        if channel in self.channels:
            list_users = " ".join(str(client.nick) for client in self.channels[channel].users if client in self.clients)
            return f":353 {channel} :{list_users}"
        return f':401 :{self.NUMERIC_REPLIES['401']}'

    def whois_user(self,client_socket, user):
        client = next((item for item in self.clients if item.nick == user), None)
        if client and not client.visibility and client.socket != client_socket:         
            return f':401 :{self.NUMERIC_REPLIES['401']}'
        else: return f':312 host:{client_socket.getpeername()[0]} nick:{client.nick}'

    def handle_topic(self, client_socket, argument):
        try:
            parts= argument.split(" ")
            channel= parts[0]
            if len(parts)>1:
                new_topic = " ".join(parts[1:])
                return self.change_topic(client_socket, channel, new_topic)
            return self.show_topic(client_socket, channel)
        except IndexError:
            return 'Error: Uso correcto /topic <channel> [new_topic]'


    def change_topic(self, client_socket, channel, new_topic):
        if not channel in self.channels:
            return  f':401 :{self.NUMERIC_REPLIES['401']}'
        
        client = next((item for item in self.clients if item.socket == client_socket), None)

        if not self.channels[channel].is_on_channel(client):
            return f':442 {channel} :{self.NUMERIC_REPLIES['442']}'
        
        if self.channels[channel].t and not self.channels[channel].is_operator(client):
            return f":482 {channel} :{self.NUMERIC_REPLIES['482']}"
        
        self.channels[channel].topic = new_topic
        self.channels[channel].broadcast(f':{client.nick}! TOPIC {channel} {new_topic}', client)
        return f':{client.nick}! TOPIC {channel} {new_topic}'


    def show_topic(self, client_socket, channel):
        client = next((item for item in self.clients if item.socket == client_socket), None)      
        if channel in self.channels:
            return f':332 {channel} {self.channels[channel].topic}'
        return f':401 :{self.NUMERIC_REPLIES['401']}'
        

    def kick_user(self, client_socket, argument):
        try:    
            parts = argument.split(" ", 2)
            channel = parts[0]
            user = parts[1]
            reason = parts[2] if len(parts) > 2 else "No reason given"    
            sender = next((item for item in self.clients if item.socket == client_socket), None)
            addressee= next((item for item in self.clients if item.nick == user), None)
            if channel in self.channels:
                if self.channels[channel].is_on_channel(sender):
                    if self.channels[channel].is_on_channel(addressee):
                        if self.channels[channel].is_operator(sender):
                            self.channels[channel].remove_user(addressee)
                            addressee.send_message(f'Has sido expulsado del canal {channel} por {reason}')
                            self.channels[channel].broadcast(f":{sender.nick}! KICK {channel} {addressee.nick} :{reason}", sender)
                            return f":{sender.nick}! KICK {channel} {addressee.nick} :{reason}"
                        return f":482 {channel} :{self.NUMERIC_REPLIES['482']}"
                    return f':441 {channel}: {self.NUMERIC_REPLIES['441']}'  
                return f':442 {channel} :{self.NUMERIC_REPLIES['442']}' 
            return  f':401 :{self.NUMERIC_REPLIES['401']}'
        except IndexError:
            return f":461 :{self.NUMERIC_REPLIES['461']}"


    def remove_client_from_channels(self, client):
        for _, channel in self.channels.items():
            channel.remove_user(client)


    def handle_mode(self, client_socket, argument):
        """Maneja el comando MODE"""
        try:
            parts = argument.split()
            target = parts[0]
            mode = parts[1] if len(parts) > 1 else ""
            param = parts[2] if len(parts) > 2 else ""

            if mode.startswith('+') or mode.startswith('-'):
                if target.startswith('#'):
                    return self.handle_channel_mode(client_socket, target, mode, param)
                else:
                    return self.handle_user_mode(client_socket, target, mode)
            return f":472 COMANDO_INVALIDO :{self.NUMERIC_REPLIES['472']}"  
        
        except Exception as e:
            return f":421 COMANDO_INVALIDO :{self.NUMERIC_REPLIES['421']}"


    def handle_channel_mode(self, client_socket, channel, mode, param):
        """Maneja modos de canal"""
        if channel not in self.channels:
            return f':401 :{self.NUMERIC_REPLIES['401']}'

        client = next((item for item in self.clients if item.socket == client_socket), None)
        # Verificar si el usuario es operador del canal
        if not self.channels[channel].is_operator(client):
            return f":482 {channel} :{self.NUMERIC_REPLIES['482']}"
        
        if len(mode)!= 2: return f":461 :{self.NUMERIC_REPLIES['461']}"

        if mode[1] == 'o': 
            user = next((item for item in self.clients if item.nick == param), None)
            if not user:
                return f':401 :{self.NUMERIC_REPLIES['401']}'
            if not self.channels[channel].is_on_channel(user):
                return f':441 {channel}: {self.NUMERIC_REPLIES['441']}'
            if mode[0] == '+':
                self.channels[channel].add_operator(user)
                user.send_message(f'El usuario {client.nick} te ha añadido como operador del canal {channel}')
            else:  
                self.channels[channel].remove_operator(user)
                user.send_message(f'El usuario {client.nick} te ha eliminado como operador del canal {channel}')

        elif mode[1] == 't':
            if mode[0] == '+':
                self.channels[channel].t= True
            else:
                self.channels[channel].t= False  

        elif mode[1] == 'm':  
            if mode[0] == '+':
                self.channels[channel].m= True
            else:
                self.channels[channel].m= False

        else: return f":472 :{self.NUMERIC_REPLIES['472']}"    

        return 'Operación Exitosa'    



    def handle_user_mode(self, client_socket, target, mode):
        """Maneja modos de usuario"""
        if target not in [client.nick for client in self.clients]:
            return f':401 :{self.NUMERIC_REPLIES['401']}'

        client = next((item for item in self.clients if item.socket == client_socket), None)
        # Un usuario solo puede cambiar sus propios modos
        if client.nick != target:
            return f":502 usuario :{self.NUMERIC_REPLIES['502']}"
        
        if len(mode)!= 2: return f":461 :{self.NUMERIC_REPLIES['461']}"

        self.clients.remove(client)

        if mode[1] == 'i':
            if mode[0] == '+':
                client.visibility = False
            else:
                client.visibility = True
        else: return f":472 :{self.NUMERIC_REPLIES['472']}"   

        self.clients.append(client)
        return 'Operación Exitosa'


if __name__ == "__main__":
    server = IRCServer()
    server.start()
