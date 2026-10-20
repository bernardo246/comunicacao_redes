import argparse
import contextlib
import io
import signal
import socket
import subprocess
import sys
import threading
import time

import client
import config
import protocol

PYTHON = sys.executable
LARGURA = 62
PORTA_FALSA = config.PORTA + 1   # porta do servidor falso do grupo E, para nao brigar com o server.py


def executar_python(argumentos, timeout=45):
    processo = subprocess.run([PYTHON] + argumentos, capture_output=True, text=True, timeout=timeout)
    return (processo.stdout + processo.stderr).strip()


def enviar_bruto(pacote, esperar_resposta=True, timeout=2):
    if isinstance(pacote, str):
        pacote = pacote.encode(config.ENCODING)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(pacote, (config.HOST, config.PORTA))
        if not esperar_resposta:
            return "(enviado, sem esperar resposta)"
        dados, _ = sock.recvfrom(config.TAM_RECV)
        return dados.decode(config.ENCODING)
    except socket.timeout:
        return "SEM RESPOSTA (timeout)"
    finally:
        sock.close()


def capturar_erro(funcao):
    try:
        funcao()
    except Exception as erro:
        return f"{type(erro).__name__}: {erro}"
    return "nenhuma excecao levantada"


def parar_servidor(processo):
    if sys.platform == "win32":
        processo.terminate()   # o Windows nao entrega SIGINT para outro processo (ValueError: Unsupported signal)
    else:
        processo.send_signal(signal.SIGINT)


def porta_ocupada():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((config.HOST, config.PORTA))
        return False
    except OSError:
        return True
    finally:
        sock.close()


# ---------------------------------------------------------------- grupo A
def a1():
    # antes rodava o auto-teste do protocol.py, que foi removido no commit 1515879; agora faz a mesma conferencia aqui
    pedido = protocol.montar_handshake_request(config.GBN, config.MODO_LOTE, 50)
    resposta = protocol.montar_handshake_ack(config.GBN, config.MODO_LOTE, 50, 5)
    lido_pedido = protocol.parsear_handshake(pedido)
    lido_resposta = protocol.parsear_handshake(resposta)
    ok = (pedido == "HS|0|712|GBN,LOTE,50"
          and resposta == "HSACK|0|809|GBN,LOTE,50,5"
          and lido_pedido["tamanho_max_texto"] == 50
          and lido_resposta["tamanho_janela"] == 5)
    return ok, f"{pedido}\n{lido_pedido}\n{resposta}\n{lido_resposta}", "HS|0|712|GBN,LOTE,50 e HSACK|0|809|GBN,LOTE,50,5, lidos de volta sem perda"


def a2():
    obtido = protocol.calcular_checksum(config.CHECKSUM_ASCII, "ABC")
    return obtido == 198, str(obtido), "198"


def a3():
    obtido = protocol.calcular_checksum(config.CHECKSUM_ASCII, "")
    return obtido == 0, str(obtido), "0"


def a4():
    pacote = protocol.montar_pacote("HS", 7, 456, "GBN,LOTE,30")
    campos = protocol.parsear_pacote(pacote)
    esperado = {"tipo": "HS", "seq": 7, "checksum": 456, "payload": "GBN,LOTE,30"}
    ok = pacote == "HS|7|456|GBN,LOTE,30" and campos == esperado
    return ok, f"{pacote}\n{campos}", f"HS|7|456|GBN,LOTE,30\n{esperado}"


def a5():
    pacote = protocol.montar_pacote("DATA", 1, 0, "texto|com|barras")
    obtido = protocol.parsear_pacote(pacote)["payload"]
    return obtido == "texto|com|barras", obtido, "texto|com|barras"


def a6():
    pacote = protocol.montar_handshake_request(config.GBN, config.MODO_LOTE, 30)
    campos = protocol.parsear_handshake(pacote)
    esperado = {
        "tipo": config.TYPE_HANDSHAKE_REQ,
        "modo_retransmissao": "GBN",
        "tipo_envio": "LOTE",
        "tamanho_max_texto": 30,
    }
    ok = pacote == "HS|0|710|GBN,LOTE,30" and campos == esperado
    return ok, f"{pacote}\n{campos}", f"HS|0|710|GBN,LOTE,30\n{esperado}"


def a7():
    pacote = protocol.montar_handshake_ack(config.SR, config.MODO_INDIVIDUAL, 50, 3)
    campos = protocol.parsear_handshake(pacote)
    esperado = {
        "tipo": config.TYPE_HANDSHAKE_ACK,
        "modo_retransmissao": "SR",
        "tipo_envio": "IND",
        "tamanho_max_texto": 50,
        "tamanho_janela": 3,
    }
    ok = pacote == "HSACK|0|668|SR,IND,50,3" and campos == esperado
    return ok, f"{pacote}\n{campos}", f"HSACK|0|668|SR,IND,50,3\n{esperado}"


# ---------------------------------------------------------------- grupo B
def b1():
    saida = executar_python(["client.py"])
    ok = "'tamanho_janela': 5" in saida and "'tamanho_max_texto': 30" in saida
    return ok, saida, "HSACK com tamanho_max_texto 30 e tamanho_janela 5"


def b2():
    linhas = []
    for _ in range(3):
        saida = executar_python(["client.py"])
        linhas.append(saida.splitlines()[-1])
    ok = all("'tamanho_janela': 5" in linha for linha in linhas)
    return ok, "\n".join(linhas), "as tres execucoes recebem o mesmo HSACK"


def b3():
    saida = executar_python(["client.py", "--modo", "SR", "--envio", "IND", "--texto", "77"])
    ok = ("HS|0|582|SR,IND,77" in saida
          and "'modo_retransmissao': 'SR'" in saida
          and "'tipo_envio': 'IND'" in saida
          and "'tamanho_max_texto': 77" in saida)
    return ok, saida, "HS|0|582|SR,IND,77 e HSACK confirmando SR, IND e 77"


def b5():
    saida_texto = executar_python(["client.py", "--texto", "5"])
    saida_modo = executar_python(["client.py", "--modo", "XPTO"])
    ok = ("--texto deve ser no minimo 30" in saida_texto
          and "invalid choice" in saida_modo)
    resumo = f"{saida_texto.splitlines()[-1]}\n{saida_modo.splitlines()[-1]}"
    return ok, resumo, "os dois sao barrados pelo cliente, sem chegar na rede"


def b4():
    saida = executar_python(["client.py"], timeout=60)
    ok = "número máximo de tentativas de handshake excedido" in saida
    return ok, saida, "5 tentativas de retransmissao e depois a mensagem de erro"


def b6():
    saida = executar_python(["client.py", "ola servidor"])
    ok = ("Pacote enviado: MSG|0|348|ola " in saida
          and "ACK do seq=2 recebido" in saida
          and "Erro" not in saida)
    return ok, saida, "3 fragmentos enviados e os 3 confirmados (ACK do seq=0, 1 e 2)"


def b7():
    # '|' e o delimitador do pacote e 'é' ocupa 2 bytes em UTF-8: os dois precisam chegar intactos
    saida = executar_python(["client.py", "a|b é ç"])
    ok = "ACK do seq=1 recebido" in saida and "Erro" not in saida
    return ok, saida, "'a|b ' e 'é ç' confirmados pelo servidor"


def b8():
    vazia = executar_python(["client.py", ""])
    longa = executar_python(["client.py", "x" * 31])
    ok = ("a mensagem nao pode ser vazia" in vazia
          and "a mensagem tem 31 caracteres, acima do limite de 30" in longa)
    resumo = f"{vazia.splitlines()[-1]}\n{longa.splitlines()[-1]}"
    return ok, resumo, "mensagem vazia e mensagem acima de --texto barradas antes da rede"


def b9():
    # \udcff e o que o Windows entrega quando o terminal manda um byte que nao e texto valido
    erro = io.StringIO()
    argv_original = sys.argv
    sys.argv = ["client.py", "ola \udcff"]
    try:
        with contextlib.redirect_stderr(erro):
            client.ler_argumentos()
        codigo = 0
    except SystemExit as saida:
        codigo = saida.code
    finally:
        sys.argv = argv_original
    obtido = erro.getvalue().strip().splitlines()[-1] if erro.getvalue().strip() else "(nenhum erro)"
    ok = codigo == 2 and "nao podem ser codificados" in obtido
    return ok, obtido, "erro do argparse: caracteres que nao podem ser codificados em utf-8"


# ---------------------------------------------------------------- grupo C
def c1():
    obtido = enviar_bruto(protocol.montar_handshake_request(config.GBN, config.MODO_LOTE, 5))
    return obtido == "HSACK|0|807|GBN,LOTE,30,5", obtido, "HSACK|0|807|GBN,LOTE,30,5"


def c2():
    modo = enviar_bruto(protocol.montar_handshake_request("XPTO", config.MODO_LOTE, 30))
    envio = enviar_bruto(protocol.montar_handshake_request(config.GBN, "ZZZ", 30))
    ok = modo.startswith("SEM RESPOSTA") and envio.startswith("SEM RESPOSTA")
    return ok, f"modo invalido  -> {modo}\nenvio invalido -> {envio}", "os dois sem resposta"


def c3():
    obtido = enviar_bruto(protocol.montar_pacote(config.TYPE_HANDSHAKE_ACK, 0, 0, "GBN,LOTE,30,5"))
    return obtido.startswith("SEM RESPOSTA"), obtido, "SEM RESPOSTA (timeout)"


def c4():
    enviar_bruto(b"LIXO", esperar_resposta=False)
    enviar_bruto(bytes([0xFF, 0xFE]), esperar_resposta=False)
    time.sleep(0.3)
    depois = enviar_bruto(protocol.montar_handshake_request(config.GBN, config.MODO_LOTE, 30))
    ok = depois == "HSACK|0|807|GBN,LOTE,30,5"
    return ok, f"apos o lixo o servidor respondeu: {depois}", "HSACK|0|807|GBN,LOTE,30,5"


def c5():
    # o servidor passou a conferir o checksum do HS: checksum 1 nao bate com o payload, entao nao ha resposta
    obtido = enviar_bruto(protocol.montar_pacote(config.TYPE_HANDSHAKE_REQ, 0, 1, "GBN,LOTE,30"))
    return obtido.startswith("SEM RESPOSTA"), obtido, "SEM RESPOSTA (timeout): HS com checksum errado descartado"


# ---------------------------------------------------------------- grupo D
def d1():
    obtido = capturar_erro(lambda: protocol.parsear_pacote("HS|0|123"))
    return obtido.startswith("ValueError: not enough values to unpack"), obtido, "ValueError: not enough values to unpack (expected 4, got 3)"


def d2():
    obtido = capturar_erro(lambda: protocol.parsear_pacote("HS|abc|123|GBN,LOTE,30"))
    return obtido.startswith("ValueError: invalid literal for int()"), obtido, "ValueError: invalid literal for int() with base 10: 'abc'"


def d3():
    obtido = capturar_erro(lambda: protocol.parsear_handshake("HSACK|0|0|GBN,LOTE,30"))
    return obtido.startswith("IndexError"), obtido, "IndexError: list index out of range"


def d4():
    obtido = capturar_erro(lambda: protocol.parsear_handshake("HS|0|0|GBN"))
    return obtido.startswith("IndexError"), obtido, "IndexError: list index out of range"


def d5():
    obtido = capturar_erro(lambda: protocol.calcular_checksum("CRC32", "ABC"))
    return obtido.startswith("ValueError: Algoritmo de checksum"), obtido, "ValueError: Algoritmo de checksum nao suportado"


# ---------------------------------------------------------------- grupo E
# O cliente roda dentro deste processo, apontado para um servidor falso na PORTA_FALSA.
# O servidor falso responde o que cada teste mandar: perder pacote, mandar lixo, mentir no HSACK...
class ServidorFalso:
    def __init__(self, responder):
        self.responder = responder    # funcao(pacote, endereco, falso) -> lista do que mandar de volta
        self.recebidos = []           # tudo o que o cliente mandou, na ordem
        self.ativo = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((config.HOST, PORTA_FALSA))
        self.sock.settimeout(0.1)
        self.thread = threading.Thread(target=self.rodar, daemon=True)

    def rodar(self):
        while self.ativo:
            try:
                dados, endereco = self.sock.recvfrom(4096)
            except (socket.timeout, OSError):
                continue
            texto = dados.decode(config.ENCODING)
            self.recebidos.append(texto)
            for resposta in self.responder(protocol.parsear_pacote(texto), endereco, self):
                if isinstance(resposta, str):
                    resposta = resposta.encode(config.ENCODING)
                self.sock.sendto(resposta, endereco)

    def dados(self):
        return [pacote for pacote in self.recebidos if pacote.startswith(config.TYPE_DATA + "|")]

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *erro):
        self.ativo = False
        self.thread.join()
        self.sock.close()


def responder_padrao(pacote, endereco, falso):
    if pacote["tipo"] == config.TYPE_HANDSHAKE_REQ:
        return [protocol.montar_handshake_ack(config.GBN, config.MODO_LOTE, 30, config.JANELA_INICIAL)]
    if pacote["tipo"] == config.TYPE_DATA:
        return [protocol.montar_ack(pacote["seq"])]
    return []


def rodar_cliente(responder, mensagem="ola servidor", tentativas=None):
    """Faz handshake + envio contra o servidor falso. Devolve (codigo de saida, saida, segundos, servidor falso)."""
    originais = (client.PORTA, client.MAX_TENTATIVAS_ENVIO)
    client.PORTA = PORTA_FALSA
    if tentativas is not None:
        client.MAX_TENTATIVAS_ENVIO = tentativas   # menos tentativas = teste de desistencia mais rapido

    saida = io.StringIO()
    codigo = 0
    inicio = time.monotonic()
    falso = ServidorFalso(responder) if responder is not None else contextlib.nullcontext()
    try:
        with falso, contextlib.redirect_stdout(saida):
            sock, _ = client.enviar_handshake()
            if mensagem:
                client.enviar_mensagem(sock, mensagem)
            sock.close()
    except SystemExit as fim:
        codigo = fim.code
    finally:
        client.PORTA, client.MAX_TENTATIVAS_ENVIO = originais
    return codigo, saida.getvalue().strip(), time.monotonic() - inicio, falso


def e1():
    perdido = []
    def responder(pacote, endereco, falso):
        if pacote["tipo"] == config.TYPE_DATA and pacote["seq"] == 1 and not perdido:
            perdido.append(1)
            return []   # some com a primeira copia do seq=1
        return responder_padrao(pacote, endereco, falso)

    codigo, saida, _, falso = rodar_cliente(responder)
    esperado = ["MSG|0|348|ola ", "MSG|1|448|serv", "MSG|1|448|serv", "MSG|2|430|idor"]
    ok = codigo == 0 and falso.dados() == esperado
    return ok, saida, f"seq=1 reenviado uma vez e mensagem concluida: {esperado}"


def e2():
    def responder(pacote, endereco, falso):
        if pacote["tipo"] == config.TYPE_DATA:
            return []   # nunca confirma dados
        return responder_padrao(pacote, endereco, falso)

    codigo, saida, segundos, falso = rodar_cliente(responder, tentativas=2)
    ok = (codigo == 1
          and "o seq=0 nao foi confirmado depois de 2 tentativas" in saida
          and len(falso.dados()) == 2)
    return ok, f"{saida}\n(codigo {codigo}, {segundos:.1f}s)", "desiste do seq=0 depois de 2 envios e sai com codigo 1"


def e3():
    def responder(pacote, endereco, falso):
        if pacote["tipo"] == config.TYPE_DATA and pacote["seq"] > 0:
            return [protocol.montar_ack(pacote["seq"] - 1), protocol.montar_ack(pacote["seq"])]   # ACK velho antes do certo
        return responder_padrao(pacote, endereco, falso)

    codigo, saida, _, falso = rodar_cliente(responder)
    ok = codigo == 0 and "Descartado: nao e o esperado: MSGACK|0|0|" in saida and len(falso.dados()) == 3
    return ok, saida, "ACK repetido descartado, sem retransmissao (3 pacotes de dados)"


def e4():
    corrompido = []
    def responder(pacote, endereco, falso):
        if pacote["tipo"] == config.TYPE_DATA and not corrompido:
            corrompido.append(1)
            return [protocol.montar_pacote(config.TYPE_DATA_ACK, 0, 999, "")]   # checksum de payload vazio e 0, nao 999
        return responder_padrao(pacote, endereco, falso)

    codigo, saida, _, falso = rodar_cliente(responder)
    ok = codigo == 0 and "Descartado: checksum invalido: MSGACK|0|999|" in saida and len(falso.dados()) == 4
    return ok, saida, "ACK com checksum errado descartado e seq=0 reenviado"


def e5():
    enviado = []
    def responder(pacote, endereco, falso):
        if pacote["tipo"] == config.TYPE_DATA and not enviado:
            enviado.append(1)
            lixo = [b"LIXO", bytes([0xFF, 0xFE]), "MSGACK|abc|0|", b"X" * 2000]
            return lixo + [protocol.montar_ack(pacote["seq"])]
        return responder_padrao(pacote, endereco, falso)

    codigo, saida, _, falso = rodar_cliente(responder)
    ok = codigo == 0 and saida.count("Descartado") >= 4 and len(falso.dados()) == 3
    return ok, saida, "4 respostas lixo descartadas (texto, nao-UTF-8, seq invalido, 2000 bytes) e mensagem concluida"


def e6():
    intruso = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    forjado = []
    def responder(pacote, endereco, falso):
        if pacote["tipo"] == config.TYPE_DATA and not forjado:
            forjado.append(1)
            intruso.sendto(protocol.montar_ack(0).encode(config.ENCODING), endereco)   # ACK certo, mas de outra porta
            return []
        return responder_padrao(pacote, endereco, falso)

    try:
        codigo, saida, _, falso = rodar_cliente(responder)
    finally:
        intruso.close()
    ok = codigo == 0 and "que nao e o servidor" in saida and len(falso.dados()) == 4
    return ok, saida, "ACK vindo de outro endereco descartado e seq=0 reenviado"


def e7():
    parar = threading.Event()
    def inundar(sock, endereco):
        while not parar.is_set():
            try:
                sock.sendto(protocol.montar_ack(99).encode(config.ENCODING), endereco)
            except OSError:
                return
            time.sleep(0.05)

    def responder(pacote, endereco, falso):
        if pacote["tipo"] == config.TYPE_DATA:
            if pacote["seq"] == 0 and len(falso.dados()) == 1:
                threading.Thread(target=inundar, args=(falso.sock, endereco), daemon=True).start()
            return []   # nunca confirma; so chega ACK errado, sem parar
        return responder_padrao(pacote, endereco, falso)

    try:
        codigo, saida, segundos, _ = rodar_cliente(responder, tentativas=2)
    finally:
        parar.set()
    limite = 2 * config.TIMEOUT_ENVIO + 1.5
    ok = codigo == 1 and segundos < limite
    resumo = f"{saida.splitlines()[-1]}\n(codigo {codigo}, {segundos:.1f}s, {saida.count('Descartado')} ACKs errados descartados)"
    return ok, resumo, f"desiste em menos de {limite:.1f}s mesmo recebendo ACK errado a cada 50ms"


def responder_hsack(hsack):
    def responder(pacote, endereco, falso):
        if pacote["tipo"] == config.TYPE_HANDSHAKE_REQ:
            return [hsack]
        return responder_padrao(pacote, endereco, falso)
    return responder


def e8():
    codigo, saida, _, _ = rodar_cliente(responder_hsack(protocol.montar_handshake_ack(config.GBN, config.MODO_LOTE, 30, 9)))
    ok = codigo == 1 and "janela 9 fora da faixa 1 a 5" in saida
    return ok, saida, "HSACK com janela 9 recusado, codigo 1"


def e9():
    codigo, saida, _, _ = rodar_cliente(responder_hsack(protocol.montar_handshake_ack(config.SR, config.MODO_LOTE, 30, 5)))
    ok = codigo == 1 and "modo SR diferente do proposto (GBN)" in saida
    return ok, saida, "HSACK com modo diferente do pedido recusado, codigo 1"


def e10():
    corrompido = []
    def responder(pacote, endereco, falso):
        if pacote["tipo"] == config.TYPE_HANDSHAKE_REQ and not corrompido:
            corrompido.append(1)
            return [protocol.montar_pacote(config.TYPE_HANDSHAKE_ACK, 0, 1, "GBN,LOTE,30,5")]
        return responder_padrao(pacote, endereco, falso)

    codigo, saida, _, falso = rodar_cliente(responder, mensagem=None)
    pedidos = [pacote for pacote in falso.recebidos if pacote.startswith("HS|")]
    ok = codigo == 0 and "Descartado: checksum invalido: HSACK|0|1|" in saida and len(pedidos) == 2
    return ok, saida, "HSACK com checksum errado descartado e HS reenviado"


def e11():
    payload = "GBN,LOTE"   # falta tamanho e janela
    hsack = protocol.montar_pacote(config.TYPE_HANDSHAKE_ACK, 0, protocol.calcular_checksum(config.CHECKSUM_ASCII, payload), payload)
    codigo, saida, _, _ = rodar_cliente(responder_hsack(hsack))
    ok = codigo == 1 and "HSACK malformado" in saida
    return ok, saida, "HSACK com checksum certo mas campos faltando: erro claro, codigo 1"


def e12():
    codigo, saida, segundos, _ = rodar_cliente(None, tentativas=2)   # ninguem escutando na PORTA_FALSA
    ok = codigo == 1 and "número máximo de tentativas de handshake excedido" in saida
    return ok, f"{saida}\n(codigo {codigo}, {segundos:.1f}s)", "sem traceback: 2 tentativas e erro de handshake, codigo 1"


TESTES = [
    ("A1", "HS e HSACK montados e lidos de volta", a1, False, False),
    ("A2", "checksum ASCII de 'ABC'", a2, False, False),
    ("A3", "checksum de payload vazio", a3, False, False),
    ("A4", "ida e volta de um pacote", a4, False, False),
    ("A5", "payload contendo o delimitador |", a5, False, False),
    ("A6", "handshake de pedido (HS)", a6, False, False),
    ("A7", "handshake de resposta (HSACK)", a7, False, False),
    ("B1", "handshake bem-sucedido pelo client.py", b1, True, False),
    ("B2", "varios clientes em sequencia", b2, True, False),
    ("B3", "cliente escolhendo SR, IND e 77", b3, True, False),
    ("B5", "parametros invalidos barrados no cliente", b5, False, False),
    ("B6", "mensagem enviada e confirmada pelo servidor", b6, True, False),
    ("B7", "mensagem com '|' e acento chega intacta", b7, True, False),
    ("B8", "mensagem vazia ou longa barrada no cliente", b8, False, False),
    ("B9", "mensagem com caractere invalido barrada", b9, False, False),
    ("B4", "cliente sem servidor no ar (~5s)", b4, False, True),
    ("C1", "tamanho abaixo do minimo corrigido para 30", c1, True, False),
    ("C2", "modo e tipo de envio invalidos recusados", c2, True, False),
    ("C3", "pacote de tipo inesperado descartado", c3, True, False),
    ("C4", "pacote lixo nao derruba o servidor", c4, True, False),
    ("C5", "HS com checksum errado descartado", c5, True, False),
    ("D1", "faltam campos no pacote", d1, False, False),
    ("D2", "seq nao numerico", d2, False, False),
    ("D3", "HSACK sem a janela", d3, False, False),
    ("D4", "payload de handshake incompleto", d4, False, False),
    ("D5", "algoritmo de checksum inexistente", d5, False, False),
    ("E1", "pacote de dados perdido e reenviado", e1, False, False),
    ("E2", "servidor nunca confirma: cliente desiste", e2, False, False),
    ("E3", "ACK repetido de pacote anterior ignorado", e3, False, False),
    ("E4", "ACK com checksum errado descartado", e4, False, False),
    ("E5", "respostas lixo nao derrubam o cliente", e5, False, False),
    ("E6", "ACK vindo de outro endereco descartado", e6, False, False),
    ("E7", "enxurrada de ACK errado nao prende o cliente", e7, False, False),
    ("E8", "HSACK com janela fora de 1 a 5 recusado", e8, False, False),
    ("E9", "HSACK com modo diferente do pedido recusado", e9, False, False),
    ("E10", "HSACK com checksum errado descartado", e10, False, False),
    ("E11", "HSACK malformado encerra com erro claro", e11, False, False),
    ("E12", "handshake sem servidor sai sem traceback", e12, False, False),
]

TITULOS = {
    "A": "GRUPO A - protocolo isolado (sem rede)",
    "B": "GRUPO B - handshake completo pela rede",
    "C": "GRUPO C - validacao e robustez do servidor",
    "D": "GRUPO D - pacotes malformados (sem rede)",
    "E": "GRUPO E - robustez do cliente (servidor falso)",
}


def selecionar(alvos):
    if not alvos:
        return [teste for teste in TESTES if not teste[4]]

    escolhidos = []
    pedidos = [alvo.upper() for alvo in alvos]
    for teste in TESTES:
        if teste[0] in pedidos or teste[0][0] in pedidos:
            escolhidos.append(teste)
    return escolhidos


def imprimir_bloco(texto, prefixo="        "):
    for linha in str(texto).splitlines():
        print(prefixo + linha)


def main():
    parser = argparse.ArgumentParser(description="Bateria de testes do trabalho de redes.")
    parser.add_argument("alvos", nargs="*", help="grupo (A, B, C, D) ou teste (A1, C4...). Sem argumento roda todos.")
    parser.add_argument("--completo", action="store_true", help="inclui tambem os testes lentos (B4)")
    parser.add_argument("--silencioso", action="store_true", help="mostra so o veredito de cada teste")
    args = parser.parse_args()

    escolhidos = selecionar(args.alvos)
    if args.completo:
        escolhidos = [teste for teste in TESTES if teste in escolhidos or teste[4]]
    if not escolhidos:
        print("Nenhum teste corresponde a", " ".join(args.alvos))
        return 2

    precisa_servidor = any(teste[3] for teste in escolhidos)
    tem_b4 = any(teste[0] == "B4" for teste in escolhidos)
    servidor = None
    servidor_externo = False

    if precisa_servidor or tem_b4:
        if porta_ocupada():
            servidor_externo = True
            print(f"Ja existe algo escutando em {config.HOST}:{config.PORTA}; usando esse servidor.")
        elif precisa_servidor:
            servidor = subprocess.Popen(
                [PYTHON, "-u", "server.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            time.sleep(1)
            print(f"Servidor iniciado pelo script em {config.HOST}:{config.PORTA}.")

    passaram = 0
    falharam = 0
    pulados = []
    grupo_atual = None

    try:
        for identificador, titulo, funcao, usa_servidor, lento in escolhidos:
            grupo = identificador[0]
            if grupo != grupo_atual:
                grupo_atual = grupo
                print()
                print("=" * LARGURA)
                print(TITULOS[grupo])
                print("=" * LARGURA)

            if identificador == "B4":
                if servidor_externo:
                    pulados.append((identificador, "servidor externo no ar; feche-o para rodar o B4"))
                    print(f"{identificador}  {titulo:<48} [PULADO]")
                    continue
                if servidor is not None:
                    parar_servidor(servidor)
                    servidor.wait(timeout=5)

            try:
                ok, obtido, esperado = funcao()
            except Exception as erro:
                ok, obtido, esperado = False, f"{type(erro).__name__}: {erro}", "sem excecao"

            print(f"{identificador}  {titulo:<48} {'[OK]' if ok else '[FALHOU]'}")
            if not args.silencioso:
                imprimir_bloco(obtido)
            if not ok:
                print("        --- esperado ---")
                imprimir_bloco(esperado)

            if ok:
                passaram += 1
            else:
                falharam += 1

            if identificador == "B4" and servidor is not None:
                servidor = subprocess.Popen(
                    [PYTHON, "-u", "server.py"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                time.sleep(1)
    finally:
        log = ""
        if servidor is not None and servidor.poll() is None:
            parar_servidor(servidor)
            try:
                log = servidor.communicate(timeout=5)[0]
            except subprocess.TimeoutExpired:
                servidor.kill()
                log = servidor.communicate()[0]

        if log.strip():
            print()
            print("=" * LARGURA)
            print("LOG DO SERVIDOR")
            print("=" * LARGURA)
            print(log.strip())

    print()
    print("=" * LARGURA)
    print(f"RESUMO: {passaram} OK, {falharam} falharam, {len(pulados)} pulados")
    for identificador, motivo in pulados:
        print(f"  {identificador} pulado: {motivo}")
    print("=" * LARGURA)
    return 1 if falharam else 0


if __name__ == "__main__":
    sys.exit(main())
