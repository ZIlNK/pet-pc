import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import { api, ApiError, GlobalSettings, InstanceConfig, InstanceSummary, Memory, PetPackage } from "./api";

type Page = "instances" | "library" | "settings" | "actions" | "global" | "memory";
type Toast = { kind: "success" | "error"; message: string } | null;

const nav: Array<{ id: Page; label: string; icon: string }> = [
  { id: "instances", label: "实例", icon: "◉" },
  { id: "library", label: "宠物库", icon: "✦" },
  { id: "settings", label: "实例设置", icon: "☷" },
  { id: "actions", label: "动作", icon: "↺" },
  { id: "global", label: "全局设置", icon: "⚙" },
  { id: "memory", label: "宠物记忆", icon: "◌" },
];

function readable(error: unknown) {
  return error instanceof Error ? error.message : "发生意外，请重试。";
}
const stateLabels: Record<string, string> = { IDLE: "空闲", DRAGGING: "拖拽中", FALLING: "下落中", INERTIA: "惯性移动中", REST_REMINDER: "休息提醒", MOTION_MODE: "运动模式", ANIMATING: "播放动作中", MOVING: "移动中" };
function displayState(state: string) { return stateLabels[state] || state; }
function clone<T>(value: T): T { return JSON.parse(JSON.stringify(value)); }
function object(value: unknown): Record<string, unknown> { return value && typeof value === "object" ? value as Record<string, unknown> : {}; }
function number(value: unknown, fallback = 0) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : fallback; }
function pickedBlob(bytes: Uint8Array) { const copied = Uint8Array.from(bytes); return new Blob([copied.buffer as ArrayBuffer]); }

function Icon({ children }: { children: string }) { return <span aria-hidden="true" className="icon">{children}</span>; }
function Button({ children, variant = "primary", busy, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "quiet"; busy?: boolean }) {
  return <button className={`button button-${variant}`} disabled={busy || props.disabled} {...props}>{busy ? "正在处理…" : children}</button>;
}
function Panel({ title, eyebrow, action, children }: { title: string; eyebrow?: string; action?: ReactNode; children: ReactNode }) {
  return <section className="panel"><div className="panel-head"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h2>{title}</h2></div>{action}</div>{children}</section>;
}
function Toggle({ label, checked, onChange, hint }: { label: string; checked: boolean; onChange(value: boolean): void; hint?: string }) {
  return <label className="toggle-row"><span><strong>{label}</strong>{hint && <small>{hint}</small>}</span><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} /></label>;
}
function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) { return <label className="field"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>; }
function Empty({ title, body, action }: { title: string; body: string; action?: ReactNode }) { return <div className="empty"><div className="empty-mark">✦</div><h2>{title}</h2><p>{body}</p>{action}</div>; }
function Confirm({ open, title, body, onCancel, onConfirm, busy }: { open: boolean; title: string; body: string; onCancel(): void; onConfirm(): void; busy?: boolean }) {
  if (!open) return null;
  return <div className="modal-backdrop" role="presentation"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="confirm-title"><p className="eyebrow">不可撤销操作</p><h2 id="confirm-title">{title}</h2><p>{body}</p><div className="modal-actions"><Button variant="secondary" onClick={onCancel} disabled={busy}>取消</Button><Button variant="danger" onClick={onConfirm} busy={busy}>确认</Button></div></section></div>;
}

export function App() {
  const [page, setPage] = useState<Page>("instances");
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [instances, setInstances] = useState<InstanceSummary[]>([]);
  const [pets, setPets] = useState<PetPackage[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selected, setSelected] = useState<InstanceConfig | null>(null);
  const [global, setGlobal] = useState<GlobalSettings | null>(null);
  const [toast, setToast] = useState<Toast>(null);
  const [confirm, setConfirm] = useState<{ title: string; body: string; run(): Promise<void> } | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);

  const selectedSummary = instances.find((instance) => instance.pet_id === selectedId);
  const fail = (error: unknown) => {
    if (error instanceof ApiError && error.status === 0) {
      setConnected(false); setInstances([]); setPets([]); setSelectedId(""); setSelected(null); setGlobal(null);
    }
    setToast({ kind: "error", message: readable(error) });
  };
  const refresh = async (focusId = selectedId) => {
    setLoading(true);
    try {
      const [health, instanceData, petData, settings] = await Promise.all([api.health(), api.instances(), api.pets(), api.globalSettings()]);
      if (!health.connected) throw new ApiError("桌宠本地 API 未连接。", 0);
      setConnected(true); setInstances(instanceData.instances); setPets(petData.pets); setGlobal(settings);
      const stillSelected = instanceData.instances.some((item) => item.pet_id === focusId);
      const nextId = stillSelected ? focusId : instanceData.instances[0]?.pet_id || "";
      setSelectedId(nextId);
      setSelected(nextId ? await api.instance(nextId) : null);
    } catch (error) { fail(error); }
    finally { setLoading(false); }
  };
  useEffect(() => { void refresh(""); }, []);
  useEffect(() => { if (!selectedId || !connected) return; api.instance(selectedId).then(setSelected).catch(fail); }, [selectedId]);

  const choosePage = (target: Page) => {
    if (["settings", "actions", "memory"].includes(target) && !selectedId) {
      setPage("instances"); setToast({ kind: "error", message: "请先选择一个实例，再打开此页面。" }); return;
    }
    setPage(target);
  };
  const onCreateInstance = async (packageName: string) => {
    try { const created = await api.createInstance(packageName); setToast({ kind: "success", message: `已创建实例 ${created.pet_id}。` }); await refresh(created.pet_id); setPage("settings"); } catch (error) { fail(error); }
  };
  const requestRemove = (instance: InstanceSummary) => setConfirm({
    title: `关闭 ${instance.package}？`, body: `这会删除实例 ${instance.pet_id} 及其已保存的配置。`,
    run: async () => { await api.removeInstance(instance.pet_id); setToast({ kind: "success", message: "实例已关闭。" }); await refresh(""); },
  });
  const runConfirm = async () => { if (!confirm) return; setConfirmBusy(true); try { await confirm.run(); setConfirm(null); } catch (error) { fail(error); } finally { setConfirmBusy(false); } };

  let content: ReactNode;
  if (!connected && !loading) content = <Offline onRetry={() => void refresh()} />;
  else if (page === "instances") content = <InstancesPage instances={instances} selectedId={selectedId} onSelect={(id) => { setSelectedId(id); setPage("settings"); }} onRemove={requestRemove} onLibrary={() => setPage("library")} onRefresh={() => void refresh()} loading={loading} />;
  else if (page === "library") content = <LibraryPage pets={pets} onCreate={onCreateInstance} onChanged={(message) => { setToast({ kind: "success", message }); void refresh(selectedId); }} onError={fail} />;
  else if (page === "global") content = <GlobalPage settings={global} onSaved={async () => { setToast({ kind: "success", message: "全局设置已保存。" }); await refresh(selectedId); }} onError={fail} />;
  else if (!selected) content = <Empty title="选择一个实例" body="实例配置、动作和记忆均关联到一个正在运行的桌宠。" action={<Button onClick={() => setPage("instances")}>浏览实例</Button>} />;
  else if (page === "settings") content = <SettingsPage config={selected} pets={pets} onSaved={async (message) => { setToast({ kind: "success", message }); await refresh(selected.pet_id); }} onError={fail} />;
  else if (page === "actions") content = <ActionsPage config={selected} onSaved={async () => { setToast({ kind: "success", message: "动作配置已保存。" }); await refresh(selected.pet_id); }} onError={fail} />;
  else content = <MemoryPage config={selected} onError={fail} requestConfirm={setConfirm} />;

  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><span className="brand-orb">●</span><div><strong>桌宠</strong><small>控制中心</small></div></div><nav aria-label="控制中心导航">{nav.map((item) => <button key={item.id} className={`nav-item ${page === item.id ? "active" : ""}`} onClick={() => choosePage(item.id)}><Icon>{item.icon}</Icon>{item.label}</button>)}</nav><div className="sidebar-note"><span className={`connection-dot ${connected ? "online" : ""}`} />{connected ? "本地 API 已连接" : "未连接"}</div></aside>
    <main className="main"><header className="topbar"><div><p className="eyebrow">桌宠平台</p><h1>{nav.find((item) => item.id === page)?.label}</h1></div><div className="instance-context"><label htmlFor="instance-picker">当前实例</label><select id="instance-picker" value={selectedId} onChange={(event) => setSelectedId(event.target.value)} disabled={!connected || instances.length === 0}><option value="">未选择实例</option>{instances.map((instance) => <option key={instance.pet_id} value={instance.pet_id}>{instance.package} · {instance.pet_id}{instance.primary ? " · 主实例" : ""}</option>)}</select></div></header>
      {selectedSummary && <div className="context-ribbon"><span className="status-badge">{displayState(selectedSummary.state)}</span><span>{selectedSummary.package}</span><span className="muted">#{selectedSummary.pet_id}</span><span className="muted">{selectedSummary.position.x}, {selectedSummary.position.y}</span></div>}
      <div className="content">{content}</div>
    </main>
    {toast && <div className={`toast ${toast.kind}`} role="status"><strong>{toast.kind === "success" ? "已保存" : "需要处理"}</strong><span>{toast.message}</span><button aria-label="关闭通知" onClick={() => setToast(null)}>×</button></div>}
    <Confirm open={Boolean(confirm)} title={confirm?.title || ""} body={confirm?.body || ""} onCancel={() => setConfirm(null)} onConfirm={() => void runConfirm()} busy={confirmBusy} />
  </div>;
}

function Offline({ onRetry }: { onRetry(): void }) { return <Empty title="控制中心未连接" body="Electron 控制中心只能通过本机 127.0.0.1 API 管理正在运行的桌宠。请先启动桌宠，然后重新连接。" action={<Button onClick={onRetry}>重新连接</Button>} />; }
function InstancesPage({ instances, selectedId, onSelect, onRemove, onLibrary, onRefresh, loading }: { instances: InstanceSummary[]; selectedId: string; onSelect(id: string): void; onRemove(instance: InstanceSummary): void; onLibrary(): void; onRefresh(): void; loading: boolean }) {
  if (!loading && instances.length === 0) return <Empty title="当前没有运行中的桌宠" body="请从宠物包创建实例，再在此处进行管理。" action={<Button onClick={onLibrary}>打开宠物库</Button>} />;
  return <><div className="page-intro"><p>每张卡片代表一个拥有独立配置的桌宠。仅在打开控制中心或完成操作后刷新数据。</p><Button variant="secondary" onClick={onRefresh} busy={loading}>刷新状态</Button></div><div className="instance-grid">{instances.map((instance) => <article className={`instance-card ${selectedId === instance.pet_id ? "selected" : ""}`} key={instance.pet_id}><div className="card-orb">{instance.package.slice(0, 1).toUpperCase()}</div><div className="card-copy"><div><span className="status-badge">{displayState(instance.state)}</span>{instance.primary && <span className="primary-mark">主实例</span>}</div><h2>{instance.package}</h2><p>#{instance.pet_id} · {instance.size}px</p><p className="muted">坐标 {instance.position.x}, {instance.position.y}</p></div><div className="card-actions"><Button variant="secondary" onClick={() => onSelect(instance.pet_id)}>配置</Button><Button variant="quiet" aria-label={`关闭 ${instance.package}`} onClick={() => onRemove(instance)}>×</Button></div></article>)}</div></>;
}
function LibraryPage({ pets, onCreate, onChanged, onError }: { pets: PetPackage[]; onCreate(name: string): void; onChanged(message: string): void; onError(error: unknown): void }) {
  const [name, setName] = useState(""); const [author, setAuthor] = useState(""); const [busy, setBusy] = useState(false);
  const newPackage = async (event: FormEvent) => { event.preventDefault(); const picked = await window.controlCenter.choosePetImage(); if (!picked) return; setBusy(true); try { const data = new FormData(); data.set("name", name); data.set("author", author); data.set("image", pickedBlob(picked.bytes), picked.name); const result = await api.createPet(data); setName(""); setAuthor(""); onChanged(`已创建宠物包 ${result.name}。`); } catch (error) { onError(error); } finally { setBusy(false); } };
  const importPackage = async () => { const picked = await window.controlCenter.choosePetArchive(); if (!picked) return; setBusy(true); try { const data = new FormData(); data.set("archive", pickedBlob(picked.bytes), picked.name); data.set("overwrite", "false"); const result = await api.importPet(data); onChanged(`已导入 ${result.name}。`); } catch (error) { if (error instanceof ApiError && error.status === 409 && window.confirm("已存在同名宠物包。要重新选择压缩包并替换它吗？")) { const replacement = await window.controlCenter.choosePetArchive(); if (!replacement) return; const data = new FormData(); data.set("archive", pickedBlob(replacement.bytes), replacement.name); data.set("overwrite", "true"); try { const result = await api.importPet(data); onChanged(`已替换 ${result.name}。`); } catch (retryError) { onError(retryError); } } else onError(error); } finally { setBusy(false); } };
  return <div className="two-column"><div><div className="page-intro"><p>宠物包仍由 Python 负责保存和校验。选择一个已有宠物包可创建新的独立桌宠。</p><Button variant="secondary" onClick={() => void importPackage()} busy={busy}>导入 ZIP</Button></div><div className="package-grid">{pets.map((pet) => <article className="package-card" key={pet.name}>{pet.preview_available ? <img src={api.preview(pet.name)} alt="" /> : <div className="preview-fallback">✦</div>}<div className="package-copy"><h2>{pet.name}</h2><p>{pet.author || "未知作者"} · v{pet.version || "—"}</p><p className="muted">{pet.action_count} 个动作</p><Button onClick={() => onCreate(pet.name)}>创建实例</Button></div></article>)}</div></div><Panel title="创建宠物包" eyebrow="系统图片选择器"><form className="stack-form" onSubmit={(event) => void newPackage(event)}><Field label="宠物包名称"><input required value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：moss-fox" /></Field><Field label="作者"><input value={author} onChange={(event) => setAuthor(event.target.value)} placeholder="可选" /></Field><p className="field-note">选择图片后会打开系统文件选择器。图片将直接发送至本地 Python API 进行校验和保存。</p><Button busy={busy} type="submit">选择图片并创建</Button></form></Panel></div>;
}
function SettingsPage({ config, pets, onSaved, onError }: { config: InstanceConfig; pets: PetPackage[]; onSaved(message: string): Promise<void>; onError(error: unknown): void }) {
  const [draft, setDraft] = useState<InstanceConfig>(() => clone(config)); const [busy, setBusy] = useState(false);
  useEffect(() => setDraft(clone(config)), [config]);
  const update = (section: string, key: string, value: unknown) => setDraft((current) => ({ ...current, [section]: { ...object(current[section as keyof InstanceConfig]), [key]: value } }));
  const save = async () => { setBusy(true); try { await api.updateInstance(config.pet_id, draft); await onSaved("实例配置已保存。"); } catch (error) { onError(error); } finally { setBusy(false); } };
  const rest = object(draft.rest_reminder), movement = object(draft.movement), motion = object(draft.motion_mode), behavior = object(draft.behavior), click = object(draft.click_detection), agent = object(draft.agent);
  return <div className="settings-layout"><Panel title="身份与位置" eyebrow="实例专属"><div className="form-grid"><Field label="宠物包"><select value={draft.package} onChange={(event) => setDraft((current) => ({ ...current, package: event.target.value }))}>{pets.map((pet) => <option key={pet.name} value={pet.name}>{pet.name}</option>)}</select></Field><Field label="尺寸（像素）"><input type="number" min="32" value={number(draft.size, 200)} onChange={(event) => setDraft((current) => ({ ...current, size: number(event.target.value, 200) }))} /></Field><Field label="坐标 X"><input type="number" value={number(object(draft.position).x)} onChange={(event) => setDraft((current) => ({ ...current, position: { x: number(event.target.value), y: number(object(current.position).y) } }))} /></Field><Field label="坐标 Y"><input type="number" value={number(object(draft.position).y)} onChange={(event) => setDraft((current) => ({ ...current, position: { x: number(object(current.position).x), y: number(event.target.value) } }))} /></Field></div></Panel><Panel title="休息提醒"><div className="form-grid"><Toggle label="启用提醒" checked={Boolean(rest.enabled)} onChange={(value) => update("rest_reminder", "enabled", value)} /><Field label="间隔（分钟）"><input type="number" value={number(rest.interval_minutes, 55)} onChange={(event) => update("rest_reminder", "interval_minutes", number(event.target.value, 55))} /></Field><Field label="倒计时（秒）"><input type="number" value={number(rest.countdown_seconds, 300)} onChange={(event) => update("rest_reminder", "countdown_seconds", number(event.target.value, 300))} /></Field><Field label="提醒强度"><select value={String(rest.intensity || "normal")} onChange={(event) => update("rest_reminder", "intensity", event.target.value)}><option value="low">低</option><option value="normal">普通</option><option value="high">高</option></select></Field></div></Panel><Panel title="移动与运动模式"><div className="form-grid"><Field label="随机间隔下限（毫秒）"><input type="number" value={number(movement.random_interval_min_ms, 3000)} onChange={(event) => update("movement", "random_interval_min_ms", number(event.target.value, 3000))} /></Field><Field label="随机间隔上限（毫秒）"><input type="number" value={number(movement.random_interval_max_ms, 15000)} onChange={(event) => update("movement", "random_interval_max_ms", number(event.target.value, 15000))} /></Field><Toggle label="启用运动模式" checked={Boolean(motion.enabled)} onChange={(value) => update("motion_mode", "enabled", value)} /><Field label="默认模式"><select value={String(motion.default_mode || "random")} onChange={(event) => update("motion_mode", "default_mode", event.target.value)}><option value="random">随机</option><option value="motion">运动</option></select></Field><Field label="移动速度"><input type="number" value={number(motion.movement_speed, 5)} onChange={(event) => update("motion_mode", "movement_speed", number(event.target.value, 5))} /></Field></div></Panel><Panel title="行为与点击检测"><div className="form-grid"><Toggle label="安静模式" checked={Boolean(behavior.quiet_mode_enabled)} onChange={(value) => update("behavior", "quiet_mode_enabled", value)} /><Field label="头部动作"><input value={String(behavior.default_head_action || "head")} onChange={(event) => update("behavior", "default_head_action", event.target.value)} /></Field><Field label="身体动作"><input value={String(behavior.default_body_action || "body_tap")} onChange={(event) => update("behavior", "default_body_action", event.target.value)} /></Field><Toggle label="启用点击区域" checked={Boolean(click.enabled)} onChange={(value) => update("click_detection", "enabled", value)} /></div><Field label="点击区域（JSON）" hint="每个区域保留兼容字段：name、x、y、width、height 和 action。"><textarea rows={5} value={JSON.stringify(click.zones || [], null, 2)} onChange={(event) => { try { update("click_detection", "zones", JSON.parse(event.target.value)); } catch { /* retain last valid JSON */ } }} /></Field></Panel><Panel title="OpenClaw 智能体"><div className="form-grid"><Toggle label="启用独立智能体" checked={Boolean(agent.enabled)} onChange={(value) => update("agent", "enabled", value)} /><Field label="智能体 ID"><input value={String(agent.agent_id || "")} onChange={(event) => update("agent", "agent_id", event.target.value)} /></Field><Field label="回复长度"><select value={String(agent.reply_length || "normal")} onChange={(event) => update("agent", "reply_length", event.target.value)}><option value="short">短</option><option value="normal">普通</option><option value="long">长</option></select></Field><Field label="主动性"><select value={String(agent.initiative || "low")} onChange={(event) => update("agent", "initiative", event.target.value)}><option value="low">低</option><option value="normal">普通</option><option value="high">高</option></select></Field></div></Panel><div className="save-bar"><span>修改会发送给正在运行的平台，不会由 Electron 直接写入文件。</span><Button onClick={() => void save()} busy={busy}>保存实例设置</Button></div></div>;
}
function ActionsPage({ config, onSaved, onError }: { config: InstanceConfig; onSaved(): Promise<void>; onError(error: unknown): void }) {
  const [actions, set动作] = useState<Record<string, Record<string, unknown>>>(() => clone(config.actions || {})); const [busy, setBusy] = useState(false);
  useEffect(() => set动作(clone(config.actions || {})), [config]);
  const mutate = (name: string, change: Record<string, unknown>) => set动作((current) => ({ ...current, [name]: { ...current[name], ...change } }));
  const save = async () => { setBusy(true); try { await api.updateInstance(config.pet_id, { actions }); await onSaved(); } catch (error) { onError(error); } finally { setBusy(false); } };
  const entries = Object.entries(actions);
  return <Panel title="动作配置" eyebrow="当前实例" action={<Button onClick={() => void save()} busy={busy}>Save 个动作</Button>}>{entries.length === 0 ? <Empty title="未配置动作" body="此宠物包没有实例级动作覆盖配置。" /> : <div className="actions-list">{entries.map(([name, action]) => <div className="action-row" key={name}><div><h3>{name}</h3><p>{Array.isArray(action.animation_files) ? action.animation_files.length : 0} 个动画文件</p></div><Toggle label="启用" checked={action.enabled !== false} onChange={(value) => mutate(name, { enabled: value })} /><Field label="权重"><input type="number" min="0" value={number(action.weight, 1)} onChange={(event) => mutate(name, { weight: Math.max(0, number(event.target.value, 1)) })} /></Field></div>)}</div>}</Panel>;
}
function GlobalPage({ settings, onSaved, onError }: { settings: GlobalSettings | null; onSaved(): Promise<void>; onError(error: unknown): void }) {
  const [draft, setDraft] = useState<GlobalSettings | null>(settings ? clone(settings) : null); const [busy, setBusy] = useState(false);
  useEffect(() => setDraft(settings ? clone(settings) : null), [settings]);
  if (!draft) return <Empty title="正在加载全局设置" body="正在读取本地平台配置。" />;
  const section = (name: string) => object(draft[name]); const change = (name: string, key: string, value: unknown) => setDraft((current) => current ? { ...current, [name]: { ...object(current[name]), [key]: value } } : current);
  const save = async () => { setBusy(true); try { const payload = clone(draft); delete payload.api.running; delete payload.llm.api_key_configured; delete payload.mcp.openclaw_hooks_token_configured; delete payload.mcp.openclaw_secret_token_configured; await api.updateGlobalSettings(payload); await onSaved(); } catch (error) { onError(error); } finally { setBusy(false); } };
  const apiSettings = section("api"), startup = section("startup"), tray = section("tray"), display = section("display"), llm = section("llm"), mcp = section("mcp");
  return <div className="settings-layout"><Panel title="API 服务" eyebrow={apiSettings.running ? "运行中" : "已停止"}><div className="form-grid"><Toggle label="启用 API 服务" checked={Boolean(apiSettings.enabled)} onChange={(value) => change("api", "enabled", value)} /><Field label="主机"><input value={String(apiSettings.host || "127.0.0.1")} onChange={(event) => change("api", "host", event.target.value)} /></Field><Field label="端口"><input type="number" min="1" max="65535" value={number(apiSettings.port, 8080)} onChange={(event) => change("api", "port", number(event.target.value, 8080))} /></Field><Field label="允许的 IP（每行一个）"><textarea rows={3} value={(Array.isArray(apiSettings.allowed_ips) ? apiSettings.allowed_ips : []).join("\n")} onChange={(event) => change("api", "allowed_ips", event.target.value.split("\n").map((item) => item.trim()).filter(Boolean))} /></Field></div></Panel><Panel title="托盘与启动"><div className="form-grid"><Toggle label="登录时启动" checked={Boolean(startup.enabled)} onChange={(value) => change("startup", "enabled", value)} /><Toggle label="隐藏启动" checked={Boolean(startup.start_hidden)} onChange={(value) => change("startup", "start_hidden", value)} /><Toggle label="启用系统托盘" checked={Boolean(tray.enabled)} onChange={(value) => change("tray", "enabled", value)} /><Toggle label="最小化到托盘" checked={Boolean(tray.minimize_to_tray)} onChange={(value) => change("tray", "minimize_to_tray", value)} /></div></Panel><Panel title="显示"><div className="form-grid"><Toggle label="跨屏拖拽" checked={Boolean(display.cross_screen_drag)} onChange={(value) => change("display", "cross_screen_drag", value)} /><Toggle label="跨屏随机移动" checked={Boolean(display.cross_screen_random_walk)} onChange={(value) => change("display", "cross_screen_random_walk", value)} /><Toggle label="记住上次屏幕" checked={Boolean(display.remember_last_screen)} onChange={(value) => change("display", "remember_last_screen", value)} /><Field label="跨屏移动概率"><input type="number" step="0.1" min="0" max="1" value={number(display.cross_screen_walk_probability, 0.3)} onChange={(event) => change("display", "cross_screen_walk_probability", number(event.target.value, 0.3))} /></Field></div></Panel><Panel title="LLM"><div className="form-grid"><Toggle label="启用 LLM" checked={Boolean(llm.enabled)} onChange={(value) => change("llm", "enabled", value)} /><Field label="模型"><input value={String(llm.model || "gpt-4o-mini")} onChange={(event) => change("llm", "model", event.target.value)} /></Field><Field label="基础 URL"><input value={String(llm.base_url || "https://api.openai.com/v1")} onChange={(event) => change("llm", "base_url", event.target.value)} /></Field><Field label="最大历史记录数"><input type="number" value={number(llm.max_history, 20)} onChange={(event) => change("llm", "max_history", number(event.target.value, 20))} /></Field><Field label={llm.api_key_configured ? "API 密钥（已保存；输入可替换）" : "API 密钥"}><input type="password" autoComplete="new-password" onChange={(event) => change("llm", "api_key", event.target.value)} /></Field></div></Panel><Panel title="OpenClaw / MCP"><div className="form-grid"><Toggle label="启用 MCP" checked={Boolean(mcp.enabled)} onChange={(value) => change("mcp", "enabled", value)} /><Field label="智能体传输方式"><select value={String(mcp.openclaw_agent_transport || "hooks")} onChange={(event) => change("mcp", "openclaw_agent_transport", event.target.value)}><option value="hooks">Hooks 回调</option><option value="channel">通道</option></select></Field><Field label="通道 URL"><input value={String(mcp.openclaw_channel_url || "")} onChange={(event) => change("mcp", "openclaw_channel_url", event.target.value)} /></Field><Field label="Hooks 回调 URL"><input value={String(mcp.openclaw_hooks_url || "")} onChange={(event) => change("mcp", "openclaw_hooks_url", event.target.value)} /></Field><Field label={mcp.openclaw_hooks_token_configured ? "Hooks 回调令牌（已保存；输入可替换）" : "Hooks 回调令牌"}><input type="password" autoComplete="new-password" onChange={(event) => change("mcp", "openclaw_hooks_token", event.target.value)} /></Field><Field label={mcp.openclaw_secret_token_configured ? "密钥令牌（已保存；输入可替换）" : "密钥令牌"}><input type="password" autoComplete="new-password" onChange={(event) => change("mcp", "openclaw_secret_token", event.target.value)} /></Field></div></Panel><div className="save-bar"><span>已保存的密钥不会返回给渲染进程。</span><Button onClick={() => void save()} busy={busy}>保存全局设置</Button></div></div>;
}
function MemoryPage({ config, onError, requestConfirm }: { config: InstanceConfig; onError(error: unknown): void; requestConfirm(value: { title: string; body: string; run(): Promise<void> }): void }) {
  const [memories, setMemories] = useState<Memory[]>([]); const [text, setText] = useState(""); const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false);
  const refresh = async () => { setLoading(true); try { const result = await api.memories(config.pet_id); setMemories(result.memories); } catch (error) { onError(error); } finally { setLoading(false); } };
  useEffect(() => { void refresh(); }, [config.pet_id]);
  const add = async (event: FormEvent) => { event.preventDefault(); setBusy(true); try { await api.addMemory(config.pet_id, text); setText(""); await refresh(); } catch (error) { onError(error); } finally { setBusy(false); } };
  const deleteOne = (memory: Memory) => requestConfirm({ title: "删除这条记忆？", body: memory.text, run: async () => { await api.deleteMemory(config.pet_id, memory.id); await refresh(); } });
  const clear = () => requestConfirm({ title: "清空托管记忆？", body: "仅清空桌宠管理的区域；不相关的 MEMORY.md 内容会保留。", run: async () => { await api.clearMemories(config.pet_id); await refresh(); } });
  const agent = object(config.agent);
  return <Panel title="托管长期记忆" eyebrow={agent.enabled && agent.agent_id ? `智能体：${String(agent.agent_id)}` : "智能体不可用"} action={<Button variant="danger" onClick={clear} disabled={memories.length === 0}>全部清空</Button>}>{!agent.enabled || !agent.agent_id ? <Empty title="请先启用 OpenClaw 智能体" body="记忆属于当前所选实例中已启用的独立智能体。" /> : <><form className="memory-form" onSubmit={(event) => void add(event)}><input required maxLength={500} value={text} onChange={(event) => setText(event.target.value)} placeholder="添加长期记忆（最多 500 个字符）" /><Button type="submit" busy={busy}>添加记忆</Button></form>{loading ? <div className="loading">正在加载托管记忆…</div> : memories.length === 0 ? <div className="empty compact"><div className="empty-mark">◌</div><h2>暂无托管记忆</h2><p>只添加希望该绑定智能体长期保留的信息。</p></div> : <ul className="memory-list">{memories.map((memory) => <li key={memory.id}><p>{memory.text}</p><Button variant="quiet" onClick={() => deleteOne(memory)} aria-label="删除记忆">×</Button></li>)}</ul>}</>}</Panel>;
}
