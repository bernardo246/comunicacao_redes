# 1. PREPARAR   → criar o socket, configurar, abrir a porta, ficar escutando
# 2. ACEITAR    → aceitar a conexão de um cliente específico
# 3. RECEBER    → ler os dados que o cliente envia (o handshake, por enquanto)
# 4. PROCESSAR  → interpretar esses dados usando o protocol.py
# 5. RESPONDER  → montar e enviar a resposta (o ACK do handshake)
# 6. ENCERRAR   → fechar os sockets quando terminar

import socket

HOST = "localhost"
PORTA = 5000

def iniciar_servidor(host, porta):
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    servidor.bind((host, porta))
    servidor.listen(1)
    return servidor