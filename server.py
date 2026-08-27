# 1. PREPARAR   → criar o socket, configurar, abrir a porta (sem "listen"!)
# 2. RECEBER    → ler o datagrama que o cliente envia (recvfrom, não accept+recv)
# 3. PROCESSAR  → interpretar esses dados usando o protocol.py
# 4. RESPONDER  → montar e enviar a resposta (sendto, direto pro endereço do cliente)
# 5. ENCERRAR   → fechar o socket quando terminar
import config
import socket


def iniciar_servidor(host, porta):
    servidor = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # criando socket e definindo que é udp
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # definindo a função

    servidor.bind((host, porta)) # definindo a porta e o ip do server
    return servidor