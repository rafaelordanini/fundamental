const {
  useState, useMemo, useEffect, computeDCF, getDcfDefaults,
  formatValue, formatMillion, formatDate, valueColor, SegmentoBadge,
  Sparkline, Breakdown, AssumptionInput,
} = window.FundamentalUI;

function DcfPanel({ row }) {
  const defaults = useMemo(() => getDcfDefaults(row), [row.papel, row.history?.summary?.revenue_cagr]);
  const [growth, setGrowth] = useState(defaults.growthRate * 100);
  const [discount, setDiscount] = useState(defaults.discountRate * 100);
  const [terminal, setTerminal] = useState(defaults.terminalGrowthRate * 100);
  const [years, setYears] = useState(defaults.years);

  useEffect(() => {
    setGrowth(defaults.growthRate * 100);
    setDiscount(defaults.discountRate * 100);
    setTerminal(defaults.terminalGrowthRate * 100);
    setYears(defaults.years);
  }, [row.papel, defaults.growthRate, defaults.discountRate, defaults.terminalGrowthRate, defaults.years]);

  const assumptions = { growthRate: growth / 100, discountRate: discount / 100, terminalGrowthRate: terminal / 100, years };
  const dcf = useMemo(() => computeDCF(row, assumptions), [row, growth, discount, terminal, years]);

  function applyScenario(type) {
    if (type === "conservative") {
      setGrowth(Math.max(-5, defaults.growthRate * 100 - 3));
      setDiscount(defaults.discountRate * 100 + 2);
      setTerminal(2);
    } else if (type === "optimistic") {
      setGrowth(Math.min(15, defaults.growthRate * 100 + 3));
      setDiscount(Math.max(8, defaults.discountRate * 100 - 2));
      setTerminal(4);
    } else {
      setGrowth(defaults.growthRate * 100);
      setDiscount(defaults.discountRate * 100);
      setTerminal(defaults.terminalGrowthRate * 100);
      setYears(defaults.years);
    }
  }

  if (!dcf.available) return <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
    <h4 className="font-semibold text-amber-800">FCD indisponível para este papel</h4>
    <p className="mt-2 text-sm text-amber-700">{dcf.reason}</p>
  </div>;

  const sensitivityDiscounts = [discount - 2, discount, discount + 2];
  const sensitivityGrowth = [growth - 2, growth, growth + 2];

  return <div className="space-y-5">
    <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-indigo-500">Preço justo por FCD</div>
          <div className="mt-1 text-3xl font-bold text-indigo-800">{formatValue(dcf.fairPrice, "brl")}</div>
          <div className={"mt-1 text-sm font-semibold " + valueColor("margem", dcf.margin)}>Margem: {formatValue(dcf.margin, "pctSigned")}</div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs sm:text-right">
          <div><span className="block text-indigo-400">Cotação</span><strong className="text-indigo-800">{formatValue(row.cotacao, "brl")}</strong></div>
          <div><span className="block text-indigo-400">Confiança</span><strong className="text-indigo-800">{dcf.confidence}</strong></div>
          <div><span className="block text-indigo-400">Valor do patrimônio</span><strong className="text-indigo-800">{formatMillion(dcf.equityValueMillion)}</strong></div>
          <div><span className="block text-indigo-400">Peso da perpetuidade</span><strong className="text-indigo-800">{formatValue(dcf.terminalWeight, "pct")}</strong></div>
        </div>
      </div>
    </div>

    <section>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-gray-800">Premissas editáveis</h4>
        <div className="flex gap-1">
          <button onClick={() => applyScenario("conservative")} className="rounded border px-2 py-1 text-xs text-gray-600 hover:bg-gray-50">Conservador</button>
          <button onClick={() => applyScenario("base")} className="rounded border px-2 py-1 text-xs text-gray-600 hover:bg-gray-50">Base</button>
          <button onClick={() => applyScenario("optimistic")} className="rounded border px-2 py-1 text-xs text-gray-600 hover:bg-gray-50">Otimista</button>
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-4">
        <AssumptionInput label="Crescimento anual" value={growth} onChange={setGrowth} suffix="%" min="-20" max="30" step="0.5"/>
        <AssumptionInput label="Taxa de desconto" value={discount} onChange={setDiscount} suffix="%" min="1" max="40" step="0.5"/>
        <AssumptionInput label="Perpetuidade" value={terminal} onChange={setTerminal} suffix="%" min="-5" max="10" step="0.5"/>
        <AssumptionInput label="Anos projetados" value={years} onChange={setYears} suffix="anos" min="3" max="10" step="1"/>
      </div>
    </section>

    <section className="grid gap-3 sm:grid-cols-4">
      <div className="rounded-lg bg-gray-50 p-3 text-xs"><span className="block text-gray-400">FCL normalizado</span><strong>{formatMillion(dcf.baseFreeCashFlowMillion)}</strong></div>
      <div className="rounded-lg bg-gray-50 p-3 text-xs"><span className="block text-gray-400">Anos de FCL</span><strong>{dcf.freeCashFlowYears}</strong></div>
      <div className="rounded-lg bg-gray-50 p-3 text-xs"><span className="block text-gray-400">Anos com FCL positivo</span><strong>{formatValue(dcf.positiveFreeCashFlowYearsRatio, "pct")}</strong></div>
      <div className="rounded-lg bg-gray-50 p-3 text-xs"><span className="block text-gray-400">Ações estimadas</span><strong>{dcf.sharesMillion.toLocaleString("pt-BR", { maximumFractionDigits: 0 })} mi</strong></div>
    </section>

    <section>
      <h4 className="mb-2 text-sm font-semibold text-gray-800">Fluxos projetados</h4>
      <div className="overflow-x-auto rounded-lg border"><table className="w-full text-xs">
        <thead className="bg-gray-50 text-gray-500"><tr><th className="px-3 py-2 text-left">Ano</th><th className="px-3 py-2 text-right">FCL projetado</th><th className="px-3 py-2 text-right">Valor presente</th></tr></thead>
        <tbody>{dcf.projection.map(item => <tr key={item.year} className="border-t"><td className="px-3 py-2">{item.year}</td><td className="px-3 py-2 text-right">{formatMillion(item.freeCashFlowMillion)}</td><td className="px-3 py-2 text-right">{formatMillion(item.presentValueMillion)}</td></tr>)}</tbody>
      </table></div>
    </section>

    <section>
      <h4 className="mb-2 text-sm font-semibold text-gray-800">Sensibilidade do preço justo</h4>
      <div className="overflow-x-auto rounded-lg border"><table className="w-full text-xs">
        <thead className="bg-gray-50"><tr><th className="px-3 py-2 text-left">Cresc. \ Desconto</th>{sensitivityDiscounts.map(rate => <th key={rate} className="px-3 py-2 text-right">{rate.toFixed(1)}%</th>)}</tr></thead>
        <tbody>{sensitivityGrowth.map(growthRate => <tr key={growthRate} className="border-t">
          <td className="px-3 py-2 font-medium">{growthRate.toFixed(1)}%</td>
          {sensitivityDiscounts.map(discountRate => {
            const scenario = computeDCF(row, { ...assumptions, growthRate: growthRate / 100, discountRate: discountRate / 100 });
            return <td key={discountRate} className="px-3 py-2 text-right">{scenario.available ? formatValue(scenario.fairPrice, "brl") : "—"}</td>;
          })}
        </tr>)}</tbody>
      </table></div>
    </section>

    <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-xs text-gray-600"><strong>Metodologia:</strong> FCL aproximado = caixa líquido das atividades operacionais + caixa líquido das atividades de investimento. A base é a mediana dos últimos três anos disponíveis. O FCD é uma faixa exploratória e não altera o ranking geral.</div>
  </div>;
}

function EvidenceChips({ keys, entry }) {
  const evidence = entry?.facts?.evidencias || {};
  if (!keys?.length) return null;
  return <div className="mt-2 flex flex-wrap gap-1">{keys.map(key => {
    const item = evidence[key];
    if (!item) return null;
    return <span key={key} className="rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-[11px] text-violet-700" title={key}>{item.rotulo}: {item.formatado ?? item.valor}</span>;
  })}</div>;
}

function ClaimCard({ claim, entry, tone = "neutral" }) {
  if (!claim) return null;
  const styles = tone === "positive" ? "border-emerald-100 bg-emerald-50/60" : tone === "risk" ? "border-amber-100 bg-amber-50/60" : "border-gray-200 bg-white";
  return <div className={"rounded-lg border p-3 " + styles}>
    <p className="text-sm leading-relaxed text-gray-700">{claim.texto}</p>
    <EvidenceChips keys={claim.evidencias} entry={entry}/>
  </div>;
}

function AnalysisPanel({ row }) {
  const entry = row.analysisEntry;
  const analysis = entry?.analysis;
  if (!analysis) return <div className="rounded-xl border border-violet-200 bg-violet-50 p-5">
    <h4 className="font-semibold text-violet-800">Análise por IA ainda não disponível</h4>
    <p className="mt-2 text-sm text-violet-700">Configure o secret <code>DEEPSEEK_API_KEY</code> no GitHub e execute o workflow “Análises DeepSeek V4”. Depois disso, o texto será atualizado sempre que os fatos usados no relatório mudarem.</p>
  </div>;

  return <div className="space-y-5">
    <div className="rounded-xl border border-violet-200 bg-gradient-to-br from-violet-50 to-white p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-violet-500">Leitura do analista</div>
          <h4 className="mt-1 text-xl font-bold text-gray-900">{analysis.titulo}</h4>
          <p className="mt-3 text-sm leading-relaxed text-gray-700">{analysis.resumo}</p>
        </div>
        <div className="shrink-0 rounded-lg border border-violet-100 bg-white p-3 text-xs text-gray-500">
          <div><strong className="text-gray-700">Modelo:</strong> {entry.modelo}</div>
          <div className="mt-1"><strong className="text-gray-700">Gerada:</strong> {formatDate(entry.data_geracao)}</div>
          <div className="mt-1"><strong className="text-gray-700">Confiança:</strong> {analysis.confianca}</div>
          <div className="mt-1"><strong className="text-gray-700">Prompt:</strong> {entry.prompt_version}</div>
        </div>
      </div>
    </div>

    <section>
      <h4 className="mb-2 text-sm font-semibold text-gray-800">Tese quantitativa</h4>
      <p className="rounded-lg border border-gray-200 bg-white p-4 text-sm leading-relaxed text-gray-700">{analysis.tese}</p>
    </section>

    <div className="grid gap-5 md:grid-cols-2">
      <section>
        <h4 className="mb-2 text-sm font-semibold text-emerald-700">Pontos fortes</h4>
        <div className="space-y-2">{analysis.pontos_fortes.map((claim, index) => <ClaimCard key={index} claim={claim} entry={entry} tone="positive"/>)}</div>
      </section>
      <section>
        <h4 className="mb-2 text-sm font-semibold text-amber-700">Pontos de atenção</h4>
        <div className="space-y-2">{analysis.pontos_atencao.map((claim, index) => <ClaimCard key={index} claim={claim} entry={entry} tone="risk"/>)}</div>
      </section>
    </div>

    <section>
      <h4 className="mb-2 text-sm font-semibold text-gray-800">Leitura de valuation</h4>
      <ClaimCard claim={analysis.valuation} entry={entry}/>
    </section>

    <section>
      <h4 className="mb-2 text-sm font-semibold text-gray-800">O que mudou desde a análise anterior</h4>
      <ClaimCard claim={analysis.mudancas_desde_anterior} entry={entry}/>
    </section>

    <section>
      <h4 className="mb-2 text-sm font-semibold text-gray-800">O que monitorar</h4>
      <ul className="grid gap-2 sm:grid-cols-2">{analysis.monitorar.map((item, index) => <li key={index} className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700">• {item}</li>)}</ul>
    </section>

    {analysis.limitacoes?.length > 0 && <section className="rounded-lg border border-gray-200 bg-gray-50 p-3">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Limitações</h4>
      <ul className="mt-2 list-inside list-disc text-xs text-gray-500">{analysis.limitacoes.map((item, index) => <li key={index}>{item}</li>)}</ul>
    </section>}

    <div className="rounded-lg border border-violet-100 bg-violet-50 p-3 text-xs text-violet-700">O DeepSeek V4 redige o relatório, mas não calcula os indicadores e não altera o score. As afirmações materiais são ligadas às evidências exibidas acima. O texto não substitui a leitura dos balanços, releases e fatos relevantes.</div>
  </div>;
}

function SummaryPanel({ row }) {
  const summary = row.history?.summary;
  return <div>
    <div className="mb-4 grid gap-3 rounded-lg bg-gray-50 p-3 text-sm sm:grid-cols-2">
      <div className="flex justify-between"><span className="text-gray-500">Posição no recorte</span><strong>{row.posicaoFiltro ?? "—"}º</strong></div>
      <div className="flex justify-between"><span className="text-gray-500">Score de ranking</span><strong>{row.rankScore ?? "—"}/100</strong></div>
      <div className="flex justify-between"><span className="text-gray-500">Qualidade consolidada</span><strong>{row.qualidade ?? "—"}/100</strong></div>
      <div className="flex justify-between"><span className="text-gray-500">Qualidade atual</span><span>{row.qualidadeAtual ?? "—"}/100</span></div>
      <div className="flex justify-between"><span className="text-gray-500">Qualidade histórica</span><span>{row.qualidadeHistorica ?? "—"}/100</span></div>
      <div className="flex justify-between"><span className="text-gray-500">Preço justo ({row.modeloUsado ?? "—"})</span><span>{formatValue(row.graham ?? row.bazin, "brl")}</span></div>
      <div className="flex justify-between"><span className="text-gray-500">Margem de segurança</span><span className={valueColor("margem", row.margem)}>{formatValue(row.margem, "pctSigned")}</span></div>
    </div>
    <div className="grid gap-5 md:grid-cols-2">
      <section><h4 className="mb-2 text-sm font-semibold text-gray-800">Indicadores atuais · peso 65%</h4><Breakdown items={row.breakdown} group="Atual"/></section>
      <section><h4 className="mb-2 text-sm font-semibold text-gray-800">Histórico CVM · peso 35%</h4><Breakdown items={row.breakdown} group="Histórico"/></section>
    </div>
    {summary && <section className="mt-5 border-t pt-4">
      <div className="mb-2 flex items-center justify-between"><h4 className="text-sm font-semibold text-gray-800">Lucro líquido trimestral</h4><span className="text-xs text-gray-400">{summary.quarters_count} trimestres</span></div>
      <Sparkline values={row.history.quarters.map(item => item.net_income)} label="Evolução do lucro líquido trimestral"/>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-5">
        <div className="rounded bg-gray-50 p-2"><span className="block text-gray-400">Trimestres lucrativos</span><strong>{formatValue(summary.profitable_quarters_ratio, "pct")}</strong></div>
        <div className="rounded bg-gray-50 p-2"><span className="block text-gray-400">CAGR receita</span><strong>{formatValue(summary.revenue_cagr, "pctSigned")}</strong></div>
        <div className="rounded bg-gray-50 p-2"><span className="block text-gray-400">ROE TTM</span><strong>{formatValue(summary.roe_ttm, "pct")}</strong></div>
        <div className="rounded bg-gray-50 p-2"><span className="block text-gray-400">Dív. líq./PL</span><strong>{formatValue(summary.net_debt_to_equity, "num")}</strong></div>
        <div className="rounded bg-gray-50 p-2"><span className="block text-gray-400">Anos de FCL</span><strong>{summary.free_cash_flow_years_count ?? "—"}</strong></div>
      </div>
    </section>}
    {row.vetos.length > 0 && <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3"><h4 className="mb-1 text-sm font-semibold text-red-700">⚠ Vetos ativos</h4><ul className="list-inside list-disc text-sm text-red-600">{row.vetos.map(veto => <li key={veto}>{veto}</li>)}</ul></div>}
    {row.alerta && <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-700"><strong>Rebaixada a Neutro:</strong> {row.alertReasons.join("; ")}.</div>}
  </div>;
}

function DetailModal({ row, onClose }) {
  const [tab, setTab] = useState("summary");
  useEffect(() => setTab("summary"), [row?.papel]);
  if (!row) return null;
  const tabClass = active => "border-b-2 px-3 py-2 text-sm font-semibold " + (active ? "border-indigo-600 text-indigo-700" : "border-transparent text-gray-400 hover:text-gray-700");
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-40 p-4" onClick={onClose}>
    <div className="max-h-full w-full max-w-5xl overflow-y-auto rounded-xl bg-white p-5 shadow-xl" onClick={event => event.stopPropagation()}>
      <div className="mb-3 flex items-start justify-between">
        <div>
          <h3 className="flex items-center gap-2 text-lg font-bold text-gray-900">{row.papel} <SegmentoBadge value={row.segmento}/></h3>
          <p className="text-xs text-gray-400">{row.history?.company_name || "Companhia"}</p>
          <p className="mt-1 text-xs font-medium text-indigo-600">{row.setor} · {row.atividade}</p>
        </div>
        <button onClick={onClose} className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600">✕</button>
      </div>
      <div className="mb-5 flex flex-wrap gap-1 border-b">
        <button onClick={() => setTab("summary")} className={tabClass(tab === "summary")}>Resumo e histórico</button>
        <button onClick={() => setTab("dcf")} className={tabClass(tab === "dcf")}>Fluxo de Caixa Descontado</button>
        <button onClick={() => setTab("analysis")} className={tabClass(tab === "analysis")}>Análise DeepSeek V4</button>
      </div>
      {tab === "summary" ? <SummaryPanel row={row}/> : tab === "dcf" ? <DcfPanel row={row}/> : <AnalysisPanel row={row}/>} 
    </div>
  </div>;
}

Object.assign(window.FundamentalUI, { DcfPanel, AnalysisPanel, SummaryPanel, DetailModal });
