# 1. PREPARAR   → criar o socket, configurar, abrir a porta 
# 2. RECEBER    → ler o datagrama que o cliente envia 
# 3. PROCESSAR  → interpretar esses dados usando o protocol.py
# 4. RESPONDER  → montar e enviar a resposta 
# 5. ENCERRAR   → fechar o socket quando terminar
import config
import socket
import protocol

# CP3: reconhecimento negativo (exigido pelo enunciado). Pacote de controle sem payload,
# com o mesmo formato tipo|seq|checksum|payload dos outros.
TYPE_NACK = "MSGNACK"

# cria o socket do servidor e deixa ele pronto pra receber dados
def iniciar_servidor(host, porta):
    servidor = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # criando socket
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # permite reusar a porta ao reiniciar

    servidor.bind((host, porta)) # associa o socket ao ip e porta
    return servidor

def receber_dados(servidor):
    # TAM_RECV é o máximo de bytes se o datagrama for maior, o excesso é perdido.
    dados, endereco_cliente = servidor.recvfrom(config.TAM_RECV)  # Recebe os dados e o endereço, por ser UDP precisa guardar o endereço
    pacote = dados.decode(config.ENCODING) # decodifica de bytes para string
    return endereco_cliente,pacote

# Antes de enviar, o pacote atravessa o canal simulado (protocol.simular_canal),
# devolve o pacote intacto, corrompido ou perdido.
# Retorna True se algo foi enviado e False se o pacote foi perdido.
def enviar_pacote(servidor, endereco_cliente, pacote):
    resultado = protocol.simular_canal(pacote)

    # perdido: nao chama o sendto, como se o pacote sumisse na rede
    if resultado is None:
        print(f"[servidor] [SIMULACAO] PERDIDO, nao enviado para {endereco_cliente}: {pacote!r}")
        return False

    # corrompido: o canal trocou um caractere, envia mesmo assim 
    if resultado != pacote:
        print(f"[servidor] [SIMULACAO] CORROMPIDO: {pacote!r} -> {resultado!r}")

    servidor.sendto(resultado.encode(config.ENCODING), endereco_cliente) # codifica para bytes e envia
    print(f"[servidor] enviado para {endereco_cliente}: {resultado!r}")
    return True

# recebe o pacote já separado em capos
def checksum_confere(pacote):
    esperado = protocol.calcular_checksum_pacote(pacote) # recalcula o checksum do pacote (tipo, seq e payload) e compara com o que veio no pacote 
    return esperado == pacote["checksum"] # se for igual é true

#mudança foi necessária porque, no CP2, 
# pacotes de tipos diferentes chegam pelo mesmo socket
#O servidor precisa descobrir o tipo antes de interpretar o conteúdo.
# recebe o pacote já decodificado em string
def processar_pacotes(pacote_str):   
    #Parse generico para descobrir o tipo 
    base = protocol.parsear_pacote(pacote_str) # chama um parse generico e separa em 4 campos
    tipo = base["tipo"]

    if tipo == config.TYPE_HANDSHAKE_REQ: # Verifica se é uma requisição de handshake  
        
        if not checksum_confere(base): # confere o checksum e só então chama o parse especifico
            return {"tipo": tipo, "checksum_valido": False}

        info = protocol.parsear_handshake(pacote_str) #checksum certo chama o parse especifico
        info["checksum_valido"] = True  
        return info

    # não é handhake ve se é um pacote de dados
    if tipo in (config.TYPE_DATA, config.TYPE_FIM):
        return protocol.parsear_pacote_data(pacote_str) # que já devolve o checksum valido 

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

    enviar_pacote(servidor, endereco_cliente, ack) # passa pelo canal simulado antes de sair

    return ack

#Evitar falar
# UDP não tem conexão, 
# então o servidor precisa lembrar o que combinou com cada cliente
# A chave do dicionário é o endereco_cliente (IP e porta).
def criar_sessao(parametros):
    return {
        "parametros": parametros, # o que foi aceito no handshake (modo, tipo de envio, tamanho, janela);
        "seq_esperado": 0, # usado pelo GBN;
        "base": 0,  # usados pelo SR
        "buffer": {}, # usados pelo SR
        "recebidos": [], # os payloads já entregues em ordem
        "seq_final": None,  # o seq do MSGFIM, preenchido quando ele cheg
        "concluida": False, # vira True quando a mensagem foi montada e impressa
    }

# antes ficava na main
def tratar_handshake(servidor, endereco_cliente, info, sessoes):
    # checksum corrompido, descarta
    if not info["checksum_valido"]:
        print(f"[servidor] HS de {endereco_cliente} com checksum invalido, descartado")
        return

    parametros, motivo = validar_parametros(info)
    
    # Recusar se os parametros forem invalidos
    if parametros is None:
        print(f"[servidor] HS de {endereco_cliente} recusado: {motivo}")
        return

    responder_handshake(servidor, endereco_cliente, parametros)

    # Verifica se o endereço ja tem uma sessao aberta
    # criar ou reiniciar a sessão
    if endereco_cliente in sessoes:
        print(f"[servidor] {endereco_cliente} refez o handshake, sessao reiniciada")

    # Cria uma nova sessao e guarda no dicionarioS
    sessoes[endereco_cliente] = criar_sessao(parametros)

# recebe o socket,destino e seq
def enviar_ack(servidor, endereco_cliente, seq):
    ack = protocol.montar_ack(seq)                 # protocol monta a ack
    enviar_pacote(servidor, endereco_cliente, ack) # passa pelo canal simulado antes de sair

# avisa o cliente que um pacote chegou corrompido 
# O seq do pacote corrompido nao e confiavel
# entao quem chama passa um seq que vem do estado do proprio servidor.
def enviar_nack(servidor, endereco_cliente, seq):
    nack = protocol.montar_pacote_com_checksum(TYPE_NACK, seq, "")
    enviar_pacote(servidor, endereco_cliente, nack)

#lado receptor do Go-Back-N. 
# O servidor só aceita o pacote que vem exatamente na vez dele, 
# não guarda nada fora de ordem e, quando descarta algo, 
# repete o último ACK que deu.
def receber_gbn(servidor, endereco_cliente, sessao, info):
    seq = info["seq"] #guardando o número da sequencia

    # se tiver pacote e ordem certas
    if info["checksum_valido"] and seq == sessao["seq_esperado"]:
        sessao["recebidos"].append(info["payload"])  
        if info["ultimo"]:                             # o FIM foi aceito em ordem mensagem termina neste seq
            sessao["seq_final"] = seq
        enviar_ack(servidor, endereco_cliente, seq)  # confirma esse pacote
        sessao["seq_esperado"] += 1   # passa a esperar o proximo            
        return

    # checksum invalido: descarta e manda NACK do seq que o servidor esta esperando
    if not info["checksum_valido"]:
        print(f"[servidor] GBN: seq={seq} descartado, checksum invalido")
        enviar_nack(servidor, endereco_cliente, sessao["seq_esperado"])
        return

    # chegou aqui: checksum certo, mas fora de ordem
    print(f"[servidor] GBN: seq={seq} descartado, fora de ordem (esperado {sessao['seq_esperado']})")

 
    # “Essa linha só roda quando o pacote é descartado, 
    #  e quando já existe algum pacote aceito. Nesse caso o servidor repete o ACK do último pacote aceito em ordem, 
    # avisando o cliente até onde está tudo certo. 
    # Se nada foi aceito ainda, não há o que repetir, e o timeout do cliente cuida do reenvio.”
    if sessao["seq_esperado"] > 0:
        enviar_ack(servidor, endereco_cliente, sessao["seq_esperado"] - 1)

def receber_sr(servidor, endereco_cliente, sessao, info):
    # guarda os valores em variaveis
    seq = info["seq"] 
    base = sessao["base"] # o primeiro seq que ainda não foi entregue, o início da janela                         
    janela = sessao["parametros"]["tamanho_janela"]  # é o tamanho combinado no HSACK    

    # checksum corrompido, só descarta sem mandar ack
    # . No SR cada pacote tem o próprio timer no cliente, 
    # então o pacote corrompido não é confirmado, 
    # o timer dele estoura e o cliente reenvia só ele.
    if not info["checksum_valido"]:
        print(f"[servidor] SR: seq={seq} descartado, checksum invalido")
        enviar_nack(servidor, endereco_cliente, base) # base = primeiro seq ainda nao entregue
        return

    # verifica se está na dentro da janela
    # Ele manda um ACK individual 
    # e guarda o pacote num buffer indexado pelo seq
    if base <= seq < base + janela:
        enviar_ack(servidor, endereco_cliente, seq)       
        # Buffer é um dicionario aceita guardar fora da ordem (so se ele perguntar)
        if seq not in sessao["buffer"]:   # guarda no buffer 
            sessao["buffer"][seq] = info["payload"]
            if info["ultimo"]:   #  guarda o seq_final
                sessao["seq_final"] = seq

        #deslizamento da janela, 
        # perguntando se o pacote do inicio ja chegou 
        # Enquanto  for sim, o pop tira esse pacote do buffer, 
        # ele vai para recebidos e a base avança

        # Assim recebidos sempre fica em ordem, ( SO SE PERGUNTAR)
        # mesmo com pacotes chegando fora de ordem
        while sessao["base"] in sessao["buffer"]:
            sessao["recebidos"].append(sessao["buffer"].pop(sessao["base"])) # remove do buffer e add o payload
            sessao["base"] += 1 # sai do buffer e vai na ordem

        # print da janela e do que tem no buffer
        print(f"[servidor] SR: janela agora [{sessao['base']}, "
              f"{sessao['base'] + janela - 1}], buffer={sorted(sessao['buffer'])}")
        return

    #trata o caso de o ACK se perder. 
    # O servidor já entregou o pacote e moveu a janela, mas o cliente não recebeu a confirmação e reenviou. 
    # Se o seq está na janela anterior,não guardo de novo, só reenvio o ACK
    if base - janela <= seq < base:
        print(f"[servidor] SR: seq={seq} duplicado (ja entregue), reenviando ACK")
        enviar_ack(servidor, endereco_cliente, seq)
        return

    print(f"[servidor] SR: seq={seq} fora da janela [{base}, {base + janela - 1}], descartado")

# Ela faz três coisas: confere se o cliente tem sessão, 
# encaminha o pacote para o algoritmo GBN ou SE e, depois, 
# verifica se a mensagem terminou.            
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

    # verifica se a mensagem acabou
    if sessao["parametros"]["modo_retransmissao"] == config.GBN:
        proximo = sessao["seq_esperado"] # GBN proximo seq que o servidor espera
    else:
        proximo = sessao["base"] # SR primeiro seq que ainda nao foi entregue

    # so finaliza uma vez
    if not sessao["concluida"] and sessao["seq_final"] is not None and proximo > sessao["seq_final"]:
        finalizar_mensagem(endereco_cliente, sessao)

# junta os payloads mostra a mensagem completa
def finalizar_mensagem(endereco_cliente, sessao):
    texto = "".join(sessao["recebidos"])

    #a mensagem chega cifrada (RC4) e so pode ser decifrada inteira,
    # depois de remontada, porque o RC4 depende do fluxo completo.
    # ValueError: chave errada ou mensagem que nao foi cifrada
    try:
        decifrado = protocol.decifrar_mensagem(config.CHAVE_CRIPTOGRAFIA, texto)
        print(f"[servidor] MENSAGEM DECIFRADA de {endereco_cliente}: {decifrado!r}")
    except ValueError as erro:
        print(f"[servidor] nao foi possivel decifrar a mensagem de {endereco_cliente}: {erro}")

    # CP3: não zera mais a sessao. Se o ACK do MSGFIM se perder, o cliente reenvia o
    # MSGFIM. Mantendo 
    # Uma mensagem nova exige um handshake novo, que recria a sessao (tratar_handshake).
    sessao["concluida"] = True

def encerrar_servidor(servidor):
    servidor.close()

def main():
    # Cria o socket e dicionario.
    servidor = iniciar_servidor(config.HOST,config.PORTA)

    # Dicionario de todas as sessoes ativas
    sessoes = {}

    print(f"[servidor] escutando em {config.HOST}:{config.PORTA} (UDP). Ctrl+C para encerrar.")

    try:
        while True: # cada volta trata um pacote
            # recebe os dados, dois erros podem acontecer
            # chegaram bytes que não sao textos validos
            try:
                endereco_cliente, dados = receber_dados(servidor)
            except UnicodeDecodeError as erro:
                print(f"[servidor] datagrama nao decodificavel, descartado: {erro}")
                continue
            except ConnectionResetError:
                print("[servidor] cliente anterior fechou a porta (ConnectionResetError), ignorando")
                continue

            # ja chegou
            print(f"[servidor] recebido de {endereco_cliente}: {dados!r}")

            # O processar_pacotes faz o parse genérico e 
            # depois o específico. 
            # Se o pacote estiver fora do formato 
            # ValueError: veio com menos de 4 campos, ou o seq ou o checksum não são números
            # IndexError: um HS com campos faltando no payload.S
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
