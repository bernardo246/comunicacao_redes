# 1. PREPARAR   → criar o socket, configurar, abrir a porta 
# 2. RECEBER    → ler o datagrama que o cliente envia 
# 3. PROCESSAR  → interpretar esses dados usando o protocol.py
# 4. RESPONDER  → montar e enviar a resposta (sendto, direto pro endereço do cliente)
# 5. ENCERRAR   → fechar o socket quando terminar
import config
import socket
import protocol

def iniciar_servidor(host, porta):
    servidor = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # criando socket e definindo que é udp
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # definindo a função

    servidor.bind((host, porta)) # definindo a porta e o ip do server
    return servidor

def receber_dados(servidor):
    endereco_cliente, dados = servidor.recvfrom(config.TAM_RECV)  # Recebe os dados e o endereço, por ser UDP precisa guardar o endereço
    pacote = dados.decode(config.ENCODING) # decodifica de bytes para string
    return endereco_cliente,pacote

def processar_pacotes(pacote_str):   # recebe o recv e chama a função parsear do protocol
    dados = protocol.parsear_handshake(pacote_str)
    return dados