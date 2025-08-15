from __future__ import annotations
from dataclasses import dataclass, asdict
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from datetime import datetime, date
from typing import List, Dict, Optional
import argparse, json, os, textwrap

ARQ_PADRAO = "loja_dados.json"

def d2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def fmt(x: Decimal) -> str:
    return f"R$ {d2(x)}"

def now_iso() -> str:
    return datetime.now().astimezone().isoformat()

def today() -> date:
    return datetime.now().date()

def ler_decimal(prompt: str) -> Decimal:
    while True:
        s = input(prompt).strip().replace(",", ".")
        try:
            return d2(Decimal(s))
        except (InvalidOperation, ValueError):
            print("@@@ Valor inválido. Tente novamente. @@@")

def ler_inteiro(prompt: str) -> int:
    while True:
        s = input(prompt).strip()
        if s.isdigit():
            return int(s)
        print("@@@ Número inteiro inválido. @@@")

@dataclass
class Produto:
    codigo: int
    nome: str
    preco: str
    estoque: int
    @property
    def preco_dec(self) -> Decimal:
        return Decimal(self.preco)
    @preco_dec.setter
    def preco_dec(self, v: Decimal):
        self.preco = str(d2(v))
    @staticmethod
    def from_dict(d: Dict) -> "Produto":
        return Produto(**d)

@dataclass
class ItemVenda:
    codigo_produto: int
    nome_produto: str
    preco_unit: str
    quantidade: int
    total_linha: str
    @staticmethod
    def criar(p: Produto, qtd: int) -> "ItemVenda":
        total = d2(p.preco_dec * Decimal(qtd))
        return ItemVenda(
            codigo_produto=p.codigo,
            nome_produto=p.nome,
            preco_unit=str(d2(p.preco_dec)),
            quantidade=qtd,
            total_linha=str(total),
        )
    @property
    def total_dec(self) -> Decimal:
        return Decimal(self.total_linha)

@dataclass
class Venda:
    id: int
    data_hora: str
    itens: List[ItemVenda]
    subtotal: str
    desconto_percent: str
    total: str
    @property
    def subtotal_dec(self) -> Decimal:
        return Decimal(self.subtotal)
    @property
    def desconto_percent_dec(self) -> Decimal:
        return Decimal(self.desconto_percent)
    @property
    def total_dec(self) -> Decimal:
        return Decimal(self.total)
    @staticmethod
    def from_dict(d: Dict) -> "Venda":
        itens = [ItemVenda(**i) for i in d.get("itens", [])]
        return Venda(
            id=d["id"],
            data_hora=d["data_hora"],
            itens=itens,
            subtotal=d["subtotal"],
            desconto_percent=d.get("desconto_percent", "0.00"),
            total=d["total"],
        )

class Loja:
    def __init__(self):
        self.produtos: List[Produto] = []
        self.vendas: List[Venda] = []
        self._prox_id_venda = 1
        self._prox_codigo_produto = 1

    def carregar(self, caminho: str):
        if not os.path.exists(caminho): return
        with open(caminho, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.produtos = [Produto.from_dict(p) for p in data.get("produtos", [])]
        self.vendas = [Venda.from_dict(v) for v in data.get("vendas", [])]
        self._prox_id_venda = max([v.id for v in self.vendas], default=0) + 1
        self._prox_codigo_produto = max([p.codigo for p in self.produtos], default=0) + 1

    def salvar(self, caminho: str):
        data = {
            "produtos": [asdict(p) for p in self.produtos],
            "vendas": [self._venda_to_dict(v) for v in self.vendas],
        }
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _venda_to_dict(v: Venda) -> Dict:
        return {
            "id": v.id,
            "data_hora": v.data_hora,
            "itens": [asdict(i) for i in v.itens],
            "subtotal": v.subtotal,
            "desconto_percent": v.desconto_percent,
            "total": v.total,
        }

    def adicionar_produto(self, nome: str, preco: Decimal, estoque: int) -> Produto:
        p = Produto(codigo=self._prox_codigo_produto, nome=nome, preco=str(d2(preco)), estoque=estoque)
        self._prox_codigo_produto += 1
        self.produtos.append(p)
        print(f"=== Produto adicionado: [{p.codigo:03}] {p.nome} ({fmt(p.preco_dec)}) estoque={p.estoque} ===")
        return p

    def repor_estoque(self, codigo: int, quantidade: int):
        p = self.buscar_produto(codigo)
        if not p:
            print("@@@ Produto não encontrado. @@@"); return
        p.estoque += quantidade
        print(f"=== Estoque atualizado: [{p.codigo:03}] {p.nome} -> {p.estoque} ===")

    def listar_produtos(self):
        if not self.produtos:
            print("\n@@@ Nenhum produto cadastrado. @@@"); return
        print("\n======= PRODUTOS =======")
        for p in self.produtos:
            print(f"[{p.codigo:03}] {p.nome:<30} {fmt(p.preco_dec):>12}  estoque={p.estoque}")
        print("========================")

    def buscar_produto(self, codigo: int) -> Optional[Produto]:
        return next((p for p in self.produtos if p.codigo == codigo), None)

    def nova_venda(self, itens_req: List[Dict], desconto_percent: Decimal = Decimal("0")) -> Optional[Venda]:
        itens: List[ItemVenda] = []
        for req in itens_req:
            p = self.buscar_produto(req["codigo"])
            qtd = req["quantidade"]
            if not p:
                print(f"@@@ Produto {req['codigo']} inexistente. @@@"); return None
            if qtd <= 0:
                print("@@@ Quantidade inválida. @@@"); return None
            if p.estoque < qtd:
                print(f"@@@ Estoque insuficiente para {p.nome}. Disp.: {p.estoque} @@@"); return None
        for req in itens_req:
            p = self.buscar_produto(req["codigo"])
            qtd = req["quantidade"]
            itens.append(ItemVenda.criar(p, qtd))
        subtotal = d2(sum(i.total_dec for i in itens))
        desconto_percent = d2(desconto_percent)
        if desconto_percent < 0 or desconto_percent > 100:
            print("@@@ Desconto deve estar entre 0 e 100. @@@"); return None
        total = d2(subtotal * (Decimal("1") - desconto_percent/Decimal("100")))
        venda = Venda(
            id=self._prox_id_venda,
            data_hora=now_iso(),
            itens=itens,
            subtotal=str(subtotal),
            desconto_percent=str(desconto_percent),
            total=str(total),
        )
        self._prox_id_venda += 1
        for i in itens_req:
            p = self.buscar_produto(i["codigo"])
            p.estoque -= i["quantidade"]
        self.vendas.append(venda)
        self._imprimir_recibo(venda)
        return venda

    def _imprimir_recibo(self, v: Venda):
        print("\n=========== RECIBO ==========")
        dt = v.data_hora.replace("T", " ")[:19]
        print(f"Venda #{v.id}  {dt}")
        print("-----------------------------")
        for it in v.itens:
            pu = Decimal(it.preco_unit)
            print(f"[{it.codigo_produto:03}] {it.nome_produto:<20} x{it.quantidade:<3} {fmt(pu):>10}  {fmt(it.total_dec):>10}")
        print("-----------------------------")
        print(f"Subtotal: {fmt(v.subtotal_dec)}")
        print(f"Desconto: {v.desconto_percent}%")
        print(f"Total:    {fmt(v.total_dec)}")
        print("=============================\n")

    def listar_vendas(self, somente_hoje: bool = False):
        vs = self.vendas
        if somente_hoje:
            d = today().isoformat()
            vs = [v for v in vs if v.data_hora[:10] == d]
        if not vs:
            print("\n@@@ Nenhuma venda registrada. @@@"); return
        print("\n=========== VENDAS ===========")
        for v in vs:
            dt = v.data_hora.replace("T", " ")[:19]
            print(f"#{v.id:<4} {dt}  {fmt(v.total_dec)}  itens={len(v.itens)}  desc={v.desconto_percent}%")
        total = d2(sum(v.total_dec for v in vs))
        print(f"------------------------------")
        print(f"Total faturado: {fmt(total)}")
        print("==============================")

def menu():
    m = """\n
    ================ MENU ================
    [ap] Adicionar produto
    [rp] Repor estoque
    [lp] Listar produtos
    [nv] Nova venda
    [lv] Listar vendas (todas)
    [lvh] Listar vendas (hoje)
    [q]  Sair
    => """
    return input(textwrap.dedent(m)).strip().lower()

def parse_args():
    p = argparse.ArgumentParser(prog="pos-cli")
    p.add_argument("--data-file", default=ARQ_PADRAO)
    p.add_argument("--no-persist", action="store_true")
    p.add_argument("--reset", action="store_true")
    return p.parse_args()

def main():
    args = parse_args()
    loja = Loja()
    if not args.no_persist and not args.reset:
        loja.carregar(args.data_file)

    while True:
        op = menu()
        if op == "ap":
            nome = input("Nome do produto: ").strip()
            preco = ler_decimal("Preço (ex.: 19.90): ")
            est = ler_inteiro("Estoque inicial: ")
            loja.adicionar_produto(nome, preco, est)

        elif op == "rp":
            cod = ler_inteiro("Código do produto: ")
            qtd = ler_inteiro("Quantidade para repor: ")
            loja.repor_estoque(cod, qtd)

        elif op == "lp":
            loja.listar_produtos()

        elif op == "nv":
            cod = ler_inteiro("Código do produto: ")
            qtd = ler_inteiro("Quantidade: ")
            desc = ler_decimal("Desconto % (0 a 100): ")
            itens_req = [{"codigo": cod, "quantidade": qtd}]
            loja.nova_venda(itens_req, desc)

        elif op == "lv":
            loja.listar_vendas(somente_hoje=False)

        elif op == "lvh":
            loja.listar_vendas(somente_hoje=True)

        elif op == "q":
            if not args.no_persist:
                loja.salvar(args.data_file)
                print(f"Dados salvos em: {args.data_file}")
            print("Saindo..."); break

        else:
            print("Operação inválida.")

if __name__ == "__main__":
    main()
