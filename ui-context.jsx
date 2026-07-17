const {
  useState, useEffect, SegmentoBadge, SummaryPanel, DcfPanel, AnalysisPanel,
} = window.FundamentalUI;

function PercentileCard({ label, value, rank, peers }) {
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  const percent = Math.round(number * 100);
  const tone = percent >= 70 ? "border-emerald-200 bg-emerald-50 text-emerald-800" : percent >= 40 ? "border-gray-200 bg-gray-50 text-gray-700" : "border-amber-200 bg-amber-50 text-amber-800";
  return <div className={"rounded-lg border p-3 " + tone}>
    <span className="block text-xs opacity-70">{label}</span>
    <strong className="mt-1 block text-xl">{percent}º percentil</strong>
    <span className="text-xs opacity-70">{rank ? `${rank}ª posição` : "posição indisponível"}{peers ? ` entre ${peers} pares` : ""}</span>
  </div>;
}

function SectorContextPanel({ entry }) {
  const sector = entry?.facts?.comparacao_setorial;
  if (!sector) return null;
  return <section className="rounded-xl border border-sky-100 bg-sky-50/50 p-4">
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
      <div><h4 className="text-sm font-semibold text-sky-900">Comparação com o setor</h4><p className="text-xs text-sky-700">Grupo: {sector.grupo} · {sector.quantidade_de_pares} empresas</p></div>
      <span className="rounded-full border border-sky-200 bg-white px-2 py-1 text-xs text-sky-700">{sector.escopo}</span>
    </div>
    <div className="grid gap-3 sm:grid-cols-3">
      <PercentileCard label="Qualidade" value={sector.percentil_qualidade} rank={sector.posicao_qualidade} peers={sector.quantidade_de_pares}/>
      <PercentileCard label="Preço relativo" value={sector.percentil_valuation} rank={sector.posicao_valuation} peers={sector.quantidade_de_pares}/>
      <PercentileCard label="Qualidade + preço" value={sector.percentil_combinado} rank={sector.posicao_combinada} peers={sector.quantidade_de_pares}/>
    </div>
    {sector.melhores_pares?.length > 0 && <div className="mt-3 text-xs text-sky-800"><strong>Melhores no recorte:</strong> {sector.melhores_pares.map(item => item.ticker).join(", ")}</div>}
  </section>;
}

function NewsContextPanel({ entry }) {
  const items = entry?.facts?.contexto_noticioso || [];
  if (!items.length) return <section className="rounded-xl border border-gray-200 bg-gray-50 p-4"><h4 className="text-sm font-semibold text-gray-700">Notícias e mercado</h4><p className="mt-1 text-xs text-gray-500">Nenhuma notícia específica e recente foi incorporada a esta análise.</p></section>;
  return <section>
    <h4 className="mb-2 text-sm font-semibold text-gray-800">Notícias consideradas</h4>
    <div className="space-y-2">{items.map((item, index) => <a key={item.id || index} href={item.url} target="_blank" rel="noopener noreferrer" className="block rounded-lg border border-gray-200 bg-white p-3 transition hover:border-violet-200 hover:bg-violet-50/30">
      <div className="flex flex-wrap items-start justify-between gap-2"><strong className="text-sm text-gray-800">{item.titulo}</strong><span className="text-xs text-gray-400">{item.fonte}{item.data ? ` · ${new Date(item.data + "T12:00:00").toLocaleDateString("pt-BR")}` : ""}</span></div>
      {item.resumo && <p className="mt-2 text-sm leading-relaxed text-gray-600">{item.resumo}</p>}
      <div className="mt-2 flex flex-wrap gap-1 text-[11px]"><span className="rounded-full bg-gray-100 px-2 py-0.5 text-gray-600">impacto: {item.impacto || "não classificado"}</span><span className="rounded-full bg-gray-100 px-2 py-0.5 text-gray-600">horizonte: {item.horizonte || "indefinido"}</span><span className="rounded-full bg-gray-100 px-2 py-0.5 text-gray-600">incerteza: {item.incerteza || "alta"}</span></div>
    </a>)}</div>
    <p className="mt-2 text-[11px] text-gray-400">Os links abrem a publicação original. O projeto não reproduz o texto integral das matérias.</p>
  </section>;
}

function ContextualAnalysisPanel({ row }) {
  return <div className="space-y-5">
    <AnalysisPanel row={row}/>
    <SectorContextPanel entry={row.analysisEntry}/>
    <NewsContextPanel entry={row.analysisEntry}/>
  </div>;
}

function ContextDetailModal({ row, onClose }) {
  const [tab, setTab] = useState("summary");
  useEffect(() => setTab("summary"), [row?.papel]);
  if (!row) return null;
  const tabClass = active => "border-b-2 px-3 py-2 text-sm font-semibold " + (active ? "border-indigo-600 text-indigo-700" : "border-transparent text-gray-400 hover:text-gray-700");
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-40 p-4" onClick={onClose}>
    <div className="max-h-full w-full max-w-5xl overflow-y-auto rounded-xl bg-white p-5 shadow-xl" onClick={event => event.stopPropagation()}>
      <div className="mb-3 flex items-start justify-between"><div><h3 className="flex items-center gap-2 text-lg font-bold text-gray-900">{row.papel} <SegmentoBadge value={row.segmento}/></h3><p className="text-xs text-gray-400">{row.history?.company_name || "Companhia"}</p><p className="mt-1 text-xs font-medium text-indigo-600">{row.setor} · {row.atividade}</p></div><button onClick={onClose} className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600">✕</button></div>
      <div className="mb-5 flex flex-wrap gap-1 border-b"><button onClick={() => setTab("summary")} className={tabClass(tab === "summary")}>Resumo e histórico</button><button onClick={() => setTab("dcf")} className={tabClass(tab === "dcf")}>Fluxo de Caixa Descontado</button><button onClick={() => setTab("analysis")} className={tabClass(tab === "analysis")}>Análise DeepSeek V4</button></div>
      {tab === "summary" ? <SummaryPanel row={row}/> : tab === "dcf" ? <DcfPanel row={row}/> : <ContextualAnalysisPanel row={row}/>} 
    </div>
  </div>;
}

Object.assign(window.FundamentalUI, { SectorContextPanel, NewsContextPanel, ContextualAnalysisPanel, DetailModal: ContextDetailModal });
