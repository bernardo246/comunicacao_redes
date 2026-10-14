# 1. PREPARAR   → criar o socket, configurar, abrir a porta 
# 2. RECEBER    → ler o datagrama que o cliente envia 
# 3. PROCESSAR  → interpretar esses dados usando o protocol.py
# 4. RESPONDER  → montar e enviar a resposta 
# 5. ENCERRAR   → fechar o socket quando terminar
import config
import socket
import protocol

# cria o socket do servidor e deixa ele pronto pra receber dados
def iniciar_servidor(host, porta):
    servidor = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # criando socket e definindo que é udp 
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # permite reusar a porta ao reiniciar

    servidor.bind((host, porta)) # associa o socket ao ip e porta
    return servidor

def receber_dados(servidor):
    # TAM_RECV é o máximo de bytes se o datagrama for maior, o excesso é perdido.
    dados, endereco_cliente = servidor.recvfrom(config.TAM_RECV)  # Recebe os dados e o endereço, por ser UDP precisa guardar o endereço
    pacote = dados.decode(config.ENCODING) # decodifica de bytes para string
    return endereco_cliente,pacote

# recebe o pacote já separado em capos
def checksum_confere(pacote):
    esperado = protocol.calcular_checksum(config.ALGORITMO_CHECKSUM_PADRAO, pacote["payload"]) # recaucula o checksum do payload e compara com o que veio no pacote 
    return esperado == pacote["checksum"] # se for igual é true

# recebe o pacote já decodificado em string
def processar_pacotes(pacote_str):   
    #Parse generico para descobrir o tipo e conferir o checksum/ parse especifico para extrair o conteudo
    base = protocol.parsear_pacote(pacote_str) # chama um parse generico e separa em 4 campos
    tipo = base["tipo"]

    if tipo == config.TYPE_HANDSHAKE_REQ: # Verifica se é uma requisição de handshake  
        
        if not checksum_confere(base): # recalcula o checksum e compara
            return {"tipo": tipo, "checksum_valido": False}

        info = protocol.parsear_handshake(pacote_str) #checksum certo chama o parse especifico
        info["checksum_valido"] = True  
        return info

    # não é handhake ve se é um pacote de dados
    if tipo in (config.TYPE_DATA, config.TYPE_FIM):
        return protocol.parsear_pacote_data(pacote_str)

    return {"tipo": tipo}
def validar_parametros(dados):
    if dados["modo_retransmissao"] not in (config.GBN, config.SR): #  so preve esses 2 GBN, SR
        return None, f"modo de retransmissao invalido: {dados['modo_retransmissao']}"

    if dados["tipo_envio"] not in (config.MODO_LOTE, config.MODO_INDIVIDUAL): # mesma lógica para o tipo de envio
        return None, f"tipo de envio invalido: {dados['tipo_envio']}"

    tamanho = dados["tamanho_max_texto"]        # ajusta para 30	A spec define 30 como mínimo/default; ajustar é mais tolerante que recusar
    if tamanho < config.MIN_TEXTO: # verifica se é maior que o minimo
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
# Converte a string em bytes, porque sockets só transmitem bytes.
#enviar para o endereço para cliente
def responder_handshake(servidor,endereco_cliente,parametros):
    ack = protocol.montar_handshake_ack(parametros["modo_retransmissao"], parametros["tipo_envio"],parametros["tamanho_max_texto"], parametros["tamanho_janela"])

    ack_bytes = ack.encode(config.ENCODING)

    servidor.sendto(ack_bytes, endereco_cliente)
    return ack

def criar_sessao(parametros):
    return {
        "parametros": parametros,
        "seq_esperado": 0,
        "base": 0,
        "buffer": {},
        "recebidos": [],
        "seq_final": None, 
    }

def tratar_handshake(servidor, endereco_cliente, info, sessoes):
    # checksum corrompido, descarta
    if not info["checksum_valido"]:
        print(f"[servidor] HS de {endereco_cliente} com checksum invalido, descartado")
        return

    parametros, motivo = validar_parametros(info)
    
    # parametros invalidos recusa o handshake 
    if parametros is None:
        print(f"[servidor] HS de {endereco_cliente} recusado: {motivo}")
        return

    # monta e envia o hsack para o cliente com os parametros acietos
    ack = responder_handshake(servidor, endereco_cliente, parametros)
    print(f"[servidor] enviado para {endereco_cliente}: {ack}")

    # Verifica se o endereço ja tem uma sessao aberta
    if endereco_cliente in sessoes:
        print(f"[servidor] {endereco_cliente} refez o handshake, sessao reiniciada")

    # Cria uma nova sessao e guarda no dicionarioS
    sessoes[endereco_cliente] = criar_sessao(parametros)

# recebe o socket,destino e seq
def enviar_ack(servidor, endereco_cliente, seq):
    ack = protocol.montar_ack(seq)                         # protocol monta a ack
    servidor.sendto(ack.encode(config.ENCODING), endereco_cliente) # codifica para bytes e envia os bytes para o endereço
    print(f"[servidor] ACK enviado para {endereco_cliente}: {ack}")


def receber_gbn(servidor, endereco_cliente, sessao, info):
    seq = info["seq"] #guardando o número da sequencia

    # se tiver valido tanto o pacote quanto a ordem
    if info["checksum_valido"] and seq == sessao["seq_esperado"]:
        sessao["recebidos"].append(info["payload"])   
        if info["ultimo"]:                             # o FIM foi aceito em ordem mensagem termina neste seq
            sessao["seq_final"] = seq
        enviar_ack(servidor, endereco_cliente, seq)  
        sessao["seq_esperado"] += 1                    
        return

    # checksum invalido pacote vai ser descartado
    if not info["checksum_valido"]:
        motivo = "checksum invalido"
    else:
        motivo = f"fora de ordem (esperado {sessao['seq_esperado']})"
    print(f"[servidor] GBN: seq={seq} descartado, {motivo}")

    # reenvia o ultimo ack do ultimo pacote recebido com ordem para avisar que ainda está parado nele
    if sessao["seq_esperado"] > 0:
        enviar_ack(servidor, endereco_cliente, sessao["seq_esperado"] - 1)

def receber_sr(servidor, endereco_cliente, sessao, info):
    # guarda os valores em variaveis
    seq = info["seq"]
    base = sessao["base"]                                
    janela = sessao["parametros"]["tamanho_janela"]      

    # checksum corrompido, só descarta sem mandar ack
    if not info["checksum_valido"]:
        print(f"[servidor] SR: seq={seq} descartado, checksum invalido")
        return

    # verifica se está na dentro da janela
    if base <= seq < base + janela:
        enviar_ack(servidor, endereco_cliente, seq)       
        if seq not in sessao["buffer"]:   # guarda no buffer  
            sessao["buffer"][seq] = info["payload"]
            if info["ultimo"]:   #  guarda o seq_final
                sessao["seq_final"] = seq

        #deslizamento da janela, perguntando se o pacote do inicio ja chegou (enquanti for sim)
        while sessao["base"] in sessao["buffer"]:
            sessao["recebidos"].append(sessao["buffer"].pop(sessao["base"])) # remove do buffer e add o payload
            sessao["base"] += 1 # sai do buffer e vai na ordem

        # print da janela e do que tem no buffer
        print(f"[servidor] SR: janela agora [{sessao['base']}, "
              f"{sessao['base'] + janela - 1}], buffer={sorted(sessao['buffer'])}")
        return

    # verifica na janela anterior
    if base - janela <= seq < base:
        print(f"[servidor] SR: seq={seq} duplicado (ja entregue), reenviando ACK")
        enviar_ack(servidor, endereco_cliente, seq)
        return

    print(f"[servidor] SR: seq={seq} fora da janela [{base}, {base + janela - 1}], descartado")
            
def tratar_dados(servidor, endereco_cliente, info, sessoes):
    sessao = sessoes.get(endereco_cliente) # procura a sessao do cliente no dicionario

    if sessao is None:  # sem sessao sem handshake previo descarte
        print(f"[servidor] MSG de {endereco_cliente} sem handshake previo, descartado")
        return

    # consulta o modo gbn ou sr
    if sessao["parametros"]["modo_retransmissao"] == config.GBN:
        receber_gbn(servidor, endereco_cliente, sessao, info)
    else:
        receber_sr(servidor, endereco_cliente, sessao, info)

    # imprime os metadados
    print(f"[servidor] DADOS de {endereco_cliente} | seq={info['seq']} | "
          f"checksum={info['checksum']} | valido={info['checksum_valido']} | "
          f"payload={info['payload']!r}")

    # verifica se a mensagem esta completa
    if sessao["parametros"]["modo_retransmissao"] == config.GBN:
        proximo = sessao["seq_esperado"] # GBN proximo seq que o servidor espera
    else:
        proximo = sessao["base"] # SR primeiro seq que ainda nao foi entregue

    if sessao["seq_final"] is not None and proximo > sessao["seq_final"]:
        finalizar_mensagem(endereco_cliente, sessao)

# junta os payloads mostra a mensagem completa
def finalizar_mensagem(endereco_cliente, sessao):
    texto = "".join(sessao["recebidos"])

    print(f"[servidor] MENSAGEM COMPLETA de {endereco_cliente} "
          f"({sessao['seq_final']} pacotes, {len(texto)} caracteres): {texto!r}")

    # prepara a sessao para a proxima mensagem (o seq recomeça em 0)
    sessao["recebidos"] = []
    sessao["buffer"] = {}
    sessao["seq_esperado"] = 0
    sessao["base"] = 0
    sessao["seq_final"] = None

def encerrar_servidor(servidor):
    servidor.close()

def main():
    servidor = iniciar_servidor(config.HOST,config.PORTA)

    # Dicionario de todas as sessoes ativas
    sessoes = {}

    print(f"[servidor] escutando em {config.HOST}:{config.PORTA} (UDP). Ctrl+C para encerrar.")

    try:
        while True:
            try:
                endereco_cliente, dados = receber_dados(servidor)
            except UnicodeDecodeError as erro:
                print(f"[servidor] datagrama nao decodificavel, descartado: {erro}")
                continue
            except ConnectionResetError:
                print("[servidor] cliente anterior fechou a porta (ConnectionResetError), ignorando")
                continue

            print(f"[servidor] recebido de {endereco_cliente}: {dados}")

            try:
                info = processar_pacotes(dados)
            except (ValueError, IndexError) as erro:
                print(f"[servidor] pacote malformado, descartado: {erro}")
                continue

            # roteamento por tipo,cada tipo de pacote vai para a sua funcao
            if info["tipo"] == config.TYPE_HANDSHAKE_REQ:
                tratar_handshake(servidor, endereco_cliente, info, sessoes)

            elif info["tipo"] in (config.TYPE_DATA, config.TYPE_FIM):
                tratar_dados(servidor, endereco_cliente, info, sessoes)
            else:
                print(f"[servidor] tipo nao esperado: {info['tipo']}, descartado")
    except KeyboardInterrupt:
        print("\n[servidor] encerrado pelo usuario.")
    finally:
        encerrar_servidor(servidor)


if __name__ == "__main__":
    main()
