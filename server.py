# 1. PREPARAR   → criar o socket, configurar, abrir a porta 
# 2. RECEBER    → ler o datagrama que o cliente envia 
# 3. PROCESSAR  → interpretar esses dados usando o protocol.py
# 4. RESPONDER  → montar e enviar a resposta 
# 5. ENCERRAR   → fechar o socket quando terminar
import config
import socket
import protocol

def iniciar_servidor(host, porta):
    #AF_INET indica endereços IPv4 (ex.: 127.0.0.1).
    servidor = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # criando socket e definindo que é udp 
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO _REUSEADDR, 1) # permite reusar a porta ao reiniciar

    servidor.bind((host, porta)) # definindo a porta e o ip do server
    return servidor

def receber_dados(servidor):
    # TAM_RECV é o máximo de bytes lidos. Se o datagrama for maior, o excesso é perdido.
    dados, endereco_cliente = servidor.recvfrom(config.TAM_RECV)  # Recebe os dados e o endereço, por ser UDP precisa guardar o endereço
    pacote = dados.decode(config.ENCODING) # decodifica de bytes para string
    return endereco_cliente,pacote

def processar_pacotes(pacote_str):   # descobre o tipo do pacote e chama o parser certo do protocol
    tipo = protocol.parsear_pacote(pacote_str)["tipo"]  #leitura para descobrir o tipo

    if tipo == config.TYPE_HANDSHAKE_REQ:
        return protocol.parsear_handshake(pacote_str)
    if tipo == config.TYPE_DATA:
        return protocol.parsear_pacote_data(pacote_str)

    return {"tipo": tipo}  # devolve o tipo, o main decide o que fazer

def validar_parametros(dados):
    if dados["modo_retransmissao"] not in (config.GBN, config.SR): #  so preve esses 2 GBN, SR}
        return None, f"modo de retransmissao invalido: {dados['modo_retransmissao']}"

    if dados["tipo_envio"] not in (config.MODO_LOTE, config.MODO_INDIVIDUAL):
        return None, f"tipo de envio invalido: {dados['tipo_envio']}"

    tamanho = dados["tamanho_max_texto"]        # ajusta para 30	A spec define 30 como mínimo/default; ajustar é mais tolerante que recusar
    if tamanho < config.MIN_TEXTO:
        print(f"[servidor] tamanho proposto ({tamanho}) abaixo do minimo, ajustando para {config.MIN_TEXTO}")
        tamanho = config.MIN_TEXTO

    aceitos = {
        "modo_retransmissao": dados["modo_retransmissao"],
        "tipo_envio": dados["tipo_envio"],
        "tamanho_max_texto": tamanho,
        "tamanho_janela": config.JANELA_INICIAL,
    }
    return aceitos, None

#montar o pacote de resposta HSACK via protocol.montar_handshake_ack
#codificar a string do pacote para bits  # Converte a string em bytes, porque sockets só transmitem bytes.
#enviar para o endereço para cliente # Envia com sendto(bytes, endereco_cliente). Em UDP você precisa dizer o destino a cada envio. 
def responder_handshake(servidor,endereco_cliente,parametros):
    ack = protocol.montar_handshake_ack(parametros["modo_retransmissao"], parametros["tipo_envio"],parametros["tamanho_max_texto"], parametros["tamanho_janela"])

    ack_bytes = ack.encode(config.ENCODING)

    servidor.sendto(ack_bytes, endereco_cliente)
    return ack

def tratar_handshake(servidor, endereco_cliente, info):
    parametros, motivo = validar_parametros(info)
    if motivo is not None:
        print(f"[servidor] handshake recusado: {motivo}, descartado")
        return

    ack = responder_handshake(servidor, endereco_cliente, parametros)
    print(f"[servidor] enviado para {endereco_cliente}: {ack}")
    
def encerrar_servidor(servidor):
    servidor.close()

def main():
    servidor = iniciar_servidor(config.HOST,config.PORTA)
    print(f"[servidor] escutando em {config.HOST}:{config.PORTA} (UDP). Ctrl+C para encerrar.")

    try:
        while True:
            try:
                endereco_cliente, dados = receber_dados(servidor)
            except UnicodeDecodeError as erro:
                print(f"[servidor] datagrama nao decodificavel, descartado: {erro}")
                continue

            print(f"[servidor] recebido de {endereco_cliente}: {dados}")

            try:
                info = processar_pacotes(dados)
            except (ValueError, IndexError) as erro:
                print(f"[servidor] pacote malformado, descartado: {erro}")
                continue

            if info["tipo"] != config.TYPE_HANDSHAKE_REQ:
                print(f"[servidor] tipo nao esperado nesta etapa: {info['tipo']}, descartado")
                continue

            parametros, motivo = validar_parametros(info)
            if motivo is not None:
                print(f"[servidor] handshake recusado: {motivo}, descartado")
                continue

            ack = responder_handshake(servidor,endereco_cliente,parametros)
            print(f"[servidor] enviado para {endereco_cliente}: {ack}")
    except KeyboardInterrupt:
        print("\n[servidor] encerrado pelo usuario.")
    finally:
        encerrar_servidor(servidor)


if __name__ == "__main__":
    main()
