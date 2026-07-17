const {
  useState, useMemo, useEffect, HISTORICO_MIN_TRIMESTRES, computeValuation,
  COLUMNS, formatValue, formatDate, valueColor, compareRank, SegmentoBadge,
  SectorCell, ScoreBadge, QualityBar, HistoryBadge, AnalysisBadge,
  RecomendacaoBadge, DetailModal,
} = window.FundamentalUI;

function getDataUrl(filename) {
  const basePath = window.location.pathname.endsWith("/") ? window.location.pathname : window.location.pathname.replace(/[^/]+$/, "");
  const url = new URL("data/" + filename, window.location.origin + basePath);
  url.searchParams.set("v", new Date().toISOString().slice(0, 10));
  return url.toString();
}

function App() {
  const [dados, setDados] = useState(null);
  const [historico, setHistorico] = useState({ companies: {}, data_coleta: "seed" });
  const [analises, setAnalises] = useState({ companies: {}, data_geracao: "seed" });
  const [erro, setErro] = useState(null);
  const [historyWarning, setHistoryWarning] = useState(null);
  const [analysisWarning, setAnalysisWarning] = useState(null);
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState("rankScore");
  const [sortAsc, setSortAsc] = useState(false);
  const [detail, setDetail] = useState(null);
  const [soNovoMercado, setSoNovoMercado] = useState(false);
  const [soComHistorico, setSoComHistorico] = useState(false);
  const [setorSelecionado, setSetorSelecionado] = useState("");
  const [atividadeSelecionada, setAtividadeSelecionada] = useState("");

  useEffect(() => {
    fetch(getDataUrl("latest.json")).then(response => { if (!response.ok) throw new Error("HTTP " + response.status); return response.json(); }).then(setDados).catch(error => setErro(error.message));
    fetch(getDataUrl("history.json")).then(response => { if (!response.ok) throw new Error("HTTP " + response.status); return response.json(); }).then(setHistorico).catch(error => setHistoryWarning(error.message));
    fetch(getDataUrl("analysis.json")).then(response => { if (!response.ok) throw new Error("HTTP " + response.status); return response.json(); }).then(setAnalises).catch(error => setAnalysisWarning(error.message));
  }, []);

  const enriched = useMemo(() => !dados?.rows ? [] : dados.rows.map(row => computeValuation({
    ...row,
    setor: row.setor || "Não classificado",
    atividade: row.atividade || "Não classificada",
    history: historico.companies?.[row.papel] || null,
    analysisEntry: analises.companies?.[row.papel] || null,
  })), [dados, historico, analises]);

  const setores = useMemo(() => [...new Set(enriched.map(row => row.setor).filter(Boolean))].sort((a, b) => a.localeCompare(b, "pt-BR")), [enriched]);
  const atividades = useMemo(() => [...new Set((setorSelecionado ? enriched.filter(row => row.setor === setorSelecionado) : enriched).map(row => row.atividade).filter(Boolean))].sort((a, b) => a.localeCompare(b, "pt-BR")), [enriched, setorSelecionado]);

  useEffect(() => { if (atividadeSelecionada && !atividades.includes(atividadeSelecionada)) setAtividadeSelecionada(""); }, [atividades, atividadeSelecionada]);
  useEffect(() => { setSortKey("rankScore"); setSortAsc(false); }, [setorSelecionado, atividadeSelecionada]);

  const filtered = useMemo(() => {
    const term = search.trim().toUpperCase();
    const result = enriched.filter(row => {
      const searchable = [row.papel, row.history?.company_name, row.setor, row.atividade, row.analysisEntry?.analysis?.titulo].filter(Boolean).join(" ").toUpperCase();
      if (term && !searchable.includes(term)) return false;
      if (setorSelecionado && row.setor !== setorSelecionado) return false;
      if (atividadeSelecionada && row.atividade !== atividadeSelecionada) return false;
      if (soNovoMercado && row.segmento !== "NM") return false;
      if (soComHistorico && !row.historicoPronto) return false;
      return true;
    }).map(row => ({ ...row }));

    [...result].sort(compareRank).forEach((row, index) => {
      const target = result.find(item => item.papel === row.papel);
      if (target) target.posicaoFiltro = row.rankScore !== null ? index + 1 : null;
    });

    result.sort((a, b) => {
      if (sortKey === "rankScore") return sortAsc ? -compareRank(a, b) : compareRank(a, b);
      const va = a[sortKey], vb = b[sortKey];
      if (va === null || va === undefined) return 1;
      if (vb === null || vb === undefined) return -1;
      if (typeof va === "string") return sortAsc ? va.localeCompare(vb, "pt-BR") : vb.localeCompare(va, "pt-BR");
      return sortAsc ? va - vb : vb - va;
    });
    return result;
  }, [enriched, search, sortKey, sortAsc, soNovoMercado, soComHistorico, setorSelecionado, atividadeSelecionada]);

  function toggleSort(key) {
    if (key === "analysisEntry") return;
    if (key === sortKey) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(key === "papel" || key === "setor"); }
  }

  function clearFilters() {
    setSearch("");
    setSetorSelecionado("");
    setAtividadeSelecionada("");
    setSoNovoMercado(false);
    setSoComHistorico(false);
    setSortKey("rankScore");
    setSortAsc(false);
  }

  if (erro) return <div className="mx-auto mt-16 max-w-md rounded-xl border border-red-200 bg-red-50 p-6 text-center"><p className="font-semibold text-red-700">Não foi possível carregar data/latest.json</p><p className="mt-2 text-sm text-red-600">{erro}</p></div>;
  if (!dados) return <div className="mt-16 text-center text-gray-400">Carregando…</div>;

  const nCompra = filtered.filter(row => row.recomendacao === "Compra").length;
  const nVenda = filtered.filter(row => row.recomendacao === "Venda").length;
  const nRebaixados = filtered.filter(row => row.alerta).length;
  const nHistorico = filtered.filter(row => row.historicoPronto).length;
  const nAnalises = filtered.filter(row => row.analysisEntry?.analysis).length;
  const hasFilters = Boolean(search || setorSelecionado || atividadeSelecionada || soNovoMercado || soComHistorico);

  return <div className="min-h-screen p-4 md:p-6"><div className="mx-auto max-w-screen-2xl">
    <header className="mb-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">📈 Monitor IBOV</h1>
          <p className="mt-1 text-sm text-gray-500">Mercado: {formatDate(dados.data_coleta)} · Histórico CVM: {formatDate(historico.data_coleta)} · Análises: {formatDate(analises.data_geracao)}</p>
        </div>
        <input type="text" placeholder="🔍 Ticker, empresa ou setor..." value={search} onChange={event => setSearch(event.target.value)} className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-emerald-500 md:w-72"/>
      </div>
      <div className="mt-4 grid gap-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm sm:grid-cols-2 lg:grid-cols-5">
        <label className="text-xs font-semibold text-gray-500">Setor
          <select value={setorSelecionado} onChange={event => { setSetorSelecionado(event.target.value); setAtividadeSelecionada(""); }} className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-normal text-gray-700">
            <option value="">Todos os setores</option>{setores.map(setor => <option key={setor} value={setor}>{setor}</option>)}
          </select>
        </label>
        <label className="text-xs font-semibold text-gray-500">Atividade
          <select value={atividadeSelecionada} onChange={event => setAtividadeSelecionada(event.target.value)} className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-normal text-gray-700">
            <option value="">Todas as atividades</option>{atividades.map(atividade => <option key={atividade} value={atividade}>{atividade}</option>)}
          </select>
        </label>
        <label className="flex cursor-pointer items-center gap-2 self-end rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-600"><input type="checkbox" checked={soNovoMercado} onChange={event => setSoNovoMercado(event.target.checked)}/> 🛡 Só Novo Mercado</label>
        <label className="flex cursor-pointer items-center gap-2 self-end rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-600"><input type="checkbox" checked={soComHistorico} onChange={event => setSoComHistorico(event.target.checked)}/> ≥ {HISTORICO_MIN_TRIMESTRES} trimestres</label>
        <button onClick={clearFilters} disabled={!hasFilters} className="self-end rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-600 disabled:opacity-40">Limpar filtros</button>
      </div>
    </header>

    {historyWarning && <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-700">Histórico CVM indisponível ({historyWarning}).</div>}
    {analysisWarning && <div className="mb-4 rounded-lg border border-violet-200 bg-violet-50 p-3 text-xs text-violet-700">Análises DeepSeek indisponíveis ({analysisWarning}). Os números e o ranking continuam funcionando.</div>}

    <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
      <div className="rounded-xl border bg-white p-4 shadow-sm"><div className="text-sm text-gray-500">Exibidas</div><div className="mt-1 text-2xl font-bold">{filtered.length}</div><div className="text-xs text-gray-400">de {enriched.length}</div></div>
      <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4"><div className="text-sm text-indigo-700">Com histórico</div><div className="mt-1 text-2xl font-bold text-indigo-700">{nHistorico}</div></div>
      <div className="rounded-xl border border-violet-200 bg-violet-50 p-4"><div className="text-sm text-violet-700">Com análise IA</div><div className="mt-1 text-2xl font-bold text-violet-700">{nAnalises}</div></div>
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4"><div className="text-sm text-emerald-700">Compra</div><div className="mt-1 text-2xl font-bold text-emerald-700">{nCompra}</div></div>
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4"><div className="text-sm text-amber-700">Rebaixadas ⚠</div><div className="mt-1 text-2xl font-bold text-amber-700">{nRebaixados}</div></div>
      <div className="rounded-xl border border-red-200 bg-red-50 p-4"><div className="text-sm text-red-700">Venda</div><div className="mt-1 text-2xl font-bold text-red-700">{nVenda}</div></div>
    </div>

    <div className="mb-4 rounded-lg border border-blue-100 bg-blue-50 p-3 text-xs text-blue-800">ℹ O ranking mantém a melhor combinação de qualidade e preço. Abra o ticker para acessar <strong>Resumo e histórico</strong>, <strong>Fluxo de Caixa Descontado</strong> e <strong>Análise DeepSeek V4</strong>. A IA interpreta apenas fatos calculados e não altera o score.</div>

    <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
      <table className="w-full min-w-max text-sm">
        <thead><tr className="border-b bg-gray-50">{COLUMNS.map(col => <th key={col.key} onClick={() => toggleSort(col.key)} className={(col.key === "analysisEntry" ? "" : "cursor-pointer ") + "whitespace-nowrap px-3 py-3 text-left font-semibold text-gray-600 hover:bg-gray-100"}>{col.label}{sortKey === col.key ? (sortAsc ? " ↑" : " ↓") : ""}</th>)}</tr></thead>
        <tbody>
          {filtered.map(row => <tr key={row.papel} className="border-b last:border-0 hover:bg-emerald-50">{COLUMNS.map(col => <td key={col.key} className={"whitespace-nowrap px-3 py-2.5 " + valueColor(col.key, row[col.key])}>
            {col.fmt === "badge" ? <RecomendacaoBadge row={row} onDetail={setDetail}/> :
             col.fmt === "ticker" ? <button onClick={() => setDetail(row)} className="font-semibold text-indigo-700 hover:underline">{row.papel}</button> :
             col.fmt === "quality" ? <QualityBar score={row.qualidade}/> :
             col.fmt === "history" ? <HistoryBadge row={row}/> :
             col.fmt === "analysis" ? <AnalysisBadge entry={row.analysisEntry}/> :
             col.fmt === "setor" ? <SectorCell row={row}/> :
             col.fmt === "segmento" ? <SegmentoBadge value={row.segmento}/> :
             col.fmt === "score" ? <ScoreBadge value={row.rankScore} rank={row.posicaoFiltro}/> :
             formatValue(row[col.key], col.fmt)}
          </td>)}</tr>)}
          {filtered.length === 0 && <tr><td colSpan={COLUMNS.length} className="px-3 py-8 text-center text-gray-400">Nenhum ticker encontrado.</td></tr>}
        </tbody>
      </table>
    </div>

    <p className="mt-4 text-xs text-gray-400">Ferramenta educacional — <strong>não constitui recomendação de investimento</strong>. Dados atuais: Fundamentus. Histórico e fluxo de caixa: CVM. Texto analítico: DeepSeek V4 sobre fatos estruturados do projeto.</p>
    <DetailModal row={detail} onClose={() => setDetail(null)}/>
  </div></div>;
}

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
