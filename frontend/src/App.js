import React, { useState, useEffect, useCallback } from 'react';
import './App.css';

const API = process.env.REACT_APP_BACKEND_URL;

function App() {
  const [tab, setTab] = useState('dashboard');
  const [status, setStatus] = useState(null);
  const [inventory, setInventory] = useState([]);
  const [posts, setPosts] = useState([]);
  const [events, setEvents] = useState([]);
  const [changelog, setChangelog] = useState([]);
  const [architecture, setArchitecture] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedStock, setSelectedStock] = useState(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [statusRes, invRes, postsRes, eventsRes, changelogRes, archRes] = await Promise.all([
        fetch(`${API}/api/system/status`),
        fetch(`${API}/api/inventory`),
        fetch(`${API}/api/posts`),
        fetch(`${API}/api/events?limit=30`),
        fetch(`${API}/api/changelog`),
        fetch(`${API}/api/architecture`),
      ]);
      setStatus(await statusRes.json());
      setInventory(await invRes.json());
      setPosts(await postsRes.json());
      setEvents(await eventsRes.json());
      setChangelog(await changelogRes.json());
      setArchitecture(await archRes.json());
    } catch (e) {
      console.error('Fetch error:', e);
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  return (
    <div>
      <Header tab={tab} setTab={setTab} status={status} />
      <div className="main-content">
        {loading ? <LoadingState /> : (
          <>
            {tab === 'dashboard' && <DashboardTab status={status} events={events} posts={posts} />}
            {tab === 'inventory' && <InventoryTab inventory={inventory} />}
            {tab === 'posts' && <PostsTab posts={posts} />}
            {tab === 'textpreview' && <TextPreviewTab inventory={inventory} onSelectStock={setSelectedStock} selectedStock={selectedStock} />}
            {tab === 'events' && <EventsTab events={events} />}
            {tab === 'architecture' && <ArchitectureTab architecture={architecture} />}
            {tab === 'changelog' && <ChangelogTab changelog={changelog} />}
          </>
        )}
      </div>
    </div>
  );
}

function Header({ tab, setTab, status }) {
  const [showRunPanel, setShowRunPanel] = useState(false);
  const tabs = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'inventory', label: 'Inventaire' },
    { id: 'posts', label: 'Posts FB' },
    { id: 'textpreview', label: 'Preview Texte' },
    { id: 'events', label: 'Events' },
    { id: 'architecture', label: 'Architecture' },
    { id: 'changelog', label: 'Changelog' },
  ];
  const connected = status?.supabase_connected;
  return (
    <>
      <header className="header" data-testid="header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <span className="header-logo" data-testid="header-logo">KENBOT</span>
          <span className={`status-dot ${connected ? '' : 'offline'}`} data-testid="status-dot" title={connected ? 'Supabase connecte' : 'Supabase deconnecte'} />
        </div>
        <nav className="header-nav" data-testid="header-nav">
          {tabs.map(t => (
            <button key={t.id} className={tab === t.id ? 'active' : ''} onClick={() => setTab(t.id)} data-testid={`nav-${t.id}`}>
              {t.label}
            </button>
          ))}
        </nav>
        <div className="header-right">
          <button className="run-btn" onClick={() => setShowRunPanel(!showRunPanel)} data-testid="run-cron-btn">
            RUN CRON
          </button>
          <span className="version-tag" data-testid="version-tag">v{status?.version || '2.1.0'}</span>
        </div>
      </header>
      {showRunPanel && <RunPanel onClose={() => setShowRunPanel(false)} />}
    </>
  );
}

function LoadingState() {
  return (
    <div style={{ textAlign: 'center', padding: '4rem', fontFamily: 'IBM Plex Mono, monospace', color: 'var(--text-secondary)' }}>
      <div style={{ fontSize: '1.5rem', marginBottom: '1rem' }}>[ LOADING ]</div>
      <div>Chargement depuis Supabase...</div>
    </div>
  );
}

function DashboardTab({ status, events, posts }) {
  const stats = status?.stats || {};
  const inv = stats.inventory || {};
  const postStats = stats.posts || {};
  const evStats = stats.events || {};
  const lastEvent = status?.last_event;

  return (
    <div>
      <div className="stats-grid animate-in" data-testid="stats-grid">
        <div className="card animate-in delay-1">
          <div className="card-label">Vehicules actifs</div>
          <div className="card-value" data-testid="stat-active-vehicles">{inv.active || 0}</div>
          <div className="card-sub">{inv.sold || 0} vendus / {inv.total || 0} total</div>
        </div>
        <div className="card animate-in delay-2">
          <div className="card-label">Posts Facebook</div>
          <div className="card-value" data-testid="stat-active-posts">{postStats.active || 0}</div>
          <div className="card-sub">{postStats.with_photos || 0} avec photos</div>
        </div>
        <div className="card animate-in delay-3">
          <div className="card-label">Sans photos</div>
          <div className="card-value" data-testid="stat-no-photo" style={{ color: (postStats.no_photo || 0) > 0 ? 'var(--accent-red)' : 'inherit' }}>
            {postStats.no_photo || 0}
          </div>
          <div className="card-sub">a mettre a jour</div>
        </div>
        <div className="card animate-in delay-4">
          <div className="card-label">Events totaux</div>
          <div className="card-value small" data-testid="stat-events">{(evStats.total || 0).toLocaleString()}</div>
          <div className="card-sub">{lastEvent ? `Dernier: ${lastEvent.type}` : ''}</div>
        </div>
      </div>

      <div className="bento-grid">
        <div className="card animate-in">
          <div className="section-subtitle">Events recents (Supabase live)</div>
          <EventsMiniTable events={events} />
        </div>
        <div className="card animate-in">
          <div className="section-subtitle">Posts Status</div>
          <PostsMiniList posts={posts} />
        </div>
      </div>
    </div>
  );
}

function EventsMiniTable({ events }) {
  if (!events || events.length === 0) return <div style={{ color: 'var(--text-secondary)', fontFamily: 'IBM Plex Mono', fontSize: '0.8rem', padding: '1rem 0' }}>Aucun event</div>;
  return (
    <div className="table-wrap" data-testid="events-table">
      <table>
        <thead>
          <tr><th>Date</th><th>Type</th><th>Slug</th></tr>
        </thead>
        <tbody>
          {events.slice(0, 15).map((e, i) => (
            <tr key={e.id || i} data-testid={`event-row-${i}`}>
              <td>{formatDateTime(e.created_at)}</td>
              <td><EventBadge type={e.type} /></td>
              <td style={{ fontSize: '0.75rem', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.slug}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EventBadge({ type }) {
  const t = (type || '').toUpperCase();
  let cls = 'badge-info';
  if (t.includes('ERROR') || t.includes('FAIL')) cls = 'badge-error';
  else if (t.includes('NEW') || t.includes('POST') || t.includes('SUCCESS')) cls = 'badge-ok';
  else if (t.includes('SOLD')) cls = 'badge-sold';
  else if (t.includes('PRICE')) cls = 'badge-warning';
  else if (t.includes('PHOTO')) cls = 'badge-info';
  else if (t.includes('SKIP')) cls = 'badge-low';
  return <span className={`badge ${cls}`}>{t}</span>;
}

function PostsMiniList({ posts }) {
  const sorted = [...(posts || [])].sort((a, b) => (a.no_photo === b.no_photo ? 0 : a.no_photo ? -1 : 1));
  return (
    <div data-testid="posts-mini-list" style={{ maxHeight: 400, overflowY: 'auto' }}>
      {sorted.slice(0, 20).map((p, i) => (
        <div className="post-item" key={p.slug || i} data-testid={`post-item-${i}`}>
          <span className="post-stock">{p.stock}</span>
          <span className="post-title">{p.slug?.replace(/-/g, ' ').slice(0, 35)}</span>
          {p.no_photo ? (
            <span className="badge badge-no-photo">NO PHOTO</span>
          ) : (
            <span className="post-photos">{p.photo_count > 0 ? `${p.photo_count} photos` : 'OK'}</span>
          )}
          <span className={`badge ${p.status === 'ACTIVE' ? 'badge-active' : 'badge-sold'}`}>{p.status}</span>
        </div>
      ))}
    </div>
  );
}

function InventoryTab({ inventory }) {
  const [filter, setFilter] = useState('ALL');
  const filtered = filter === 'ALL' ? inventory : inventory.filter(v => v.status === filter);
  const active = inventory.filter(v => v.status === 'ACTIVE');
  const sold = inventory.filter(v => v.status === 'SOLD');

  return (
    <div>
      <h2 className="section-title" data-testid="inventory-title">Inventaire Kennebec (Supabase live)</h2>
      <div className="stats-grid" style={{ marginBottom: '1rem' }}>
        <div className="card" onClick={() => setFilter('ALL')} style={{ cursor: 'pointer', borderColor: filter === 'ALL' ? 'var(--border-heavy)' : undefined }}>
          <div className="card-label">Total</div><div className="card-value">{inventory.length}</div>
        </div>
        <div className="card" onClick={() => setFilter('ACTIVE')} style={{ cursor: 'pointer', borderColor: filter === 'ACTIVE' ? 'var(--accent-green)' : undefined }}>
          <div className="card-label">Actifs</div><div className="card-value" style={{ color: 'var(--accent-green)' }}>{active.length}</div>
        </div>
        <div className="card" onClick={() => setFilter('SOLD')} style={{ cursor: 'pointer', borderColor: filter === 'SOLD' ? 'var(--primary)' : undefined }}>
          <div className="card-label">Vendus</div><div className="card-value">{sold.length}</div>
        </div>
        <div className="card">
          <div className="card-label">Stickers PDF</div><div className="card-value small">60</div>
        </div>
      </div>
      <div className="card">
        <div className="table-wrap" data-testid="inventory-table">
          <table>
            <thead>
              <tr><th>Stock</th><th>Titre</th><th>Prix</th><th>KM</th><th>VIN</th><th>Status</th></tr>
            </thead>
            <tbody>
              {filtered.map((v, i) => (
                <tr key={v.slug || i} data-testid={`inv-row-${i}`}>
                  <td style={{ fontWeight: 600 }}>{v.stock || '--'}</td>
                  <td style={{ fontFamily: 'IBM Plex Sans, sans-serif' }}>{v.title || v.slug?.replace(/-/g, ' ') || '--'}</td>
                  <td>{v.price_int ? `${v.price_int.toLocaleString()} $` : '--'}</td>
                  <td>{v.km_int ? `${v.km_int.toLocaleString()} km` : '--'}</td>
                  <td style={{ fontSize: '0.65rem' }}>{v.vin || '--'}</td>
                  <td><span className={`badge ${v.status === 'ACTIVE' ? 'badge-active' : 'badge-sold'}`}>{v.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function PostsTab({ posts }) {
  const noPhoto = (posts || []).filter(p => p.no_photo);
  const active = (posts || []).filter(p => p.status === 'ACTIVE');
  const sold = (posts || []).filter(p => p.status === 'SOLD');

  return (
    <div>
      <h2 className="section-title" data-testid="posts-title">Posts Facebook (Supabase live)</h2>
      <div className="stats-grid" style={{ marginBottom: '1rem' }}>
        <div className="card"><div className="card-label">Total</div><div className="card-value">{(posts || []).length}</div></div>
        <div className="card"><div className="card-label">Actifs</div><div className="card-value" style={{ color: 'var(--accent-green)' }}>{active.length}</div></div>
        <div className="card"><div className="card-label">Vendus</div><div className="card-value">{sold.length}</div></div>
        <div className="card"><div className="card-label">Sans photos</div><div className="card-value" style={{ color: noPhoto.length > 0 ? 'var(--accent-red)' : 'inherit' }}>{noPhoto.length}</div></div>
      </div>

      {noPhoto.length > 0 && (
        <div className="card" style={{ borderColor: 'var(--accent-red)', borderWidth: 2, marginBottom: '1.5rem' }}>
          <div className="section-subtitle" style={{ color: 'var(--accent-red)' }}>
            Posts sans photos ({noPhoto.length}) — En attente de PHOTOS_ADDED
          </div>
          {noPhoto.map((p, i) => (
            <div className="post-item" key={p.slug || i} data-testid={`no-photo-post-${i}`}>
              <span className="post-stock">{p.stock}</span>
              <span className="post-title">{p.slug?.replace(/-/g, ' ')}</span>
              <span className="badge badge-no-photo">NO PHOTO</span>
              <span style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.65rem', color: 'var(--text-secondary)' }}>
                {p.post_id?.slice(0, 15)}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="card">
        <div className="section-subtitle">Tous les posts ({(posts || []).length})</div>
        <div className="table-wrap" data-testid="posts-table">
          <table>
            <thead><tr><th>Stock</th><th>Slug</th><th>Post ID</th><th>Publie le</th><th>Modifie le</th><th>Status</th></tr></thead>
            <tbody>
              {(posts || []).map((p, i) => (
                <tr key={p.slug || i} data-testid={`post-row-${i}`}>
                  <td style={{ fontWeight: 600 }}>{p.stock}</td>
                  <td style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.78rem' }}>{p.slug?.replace(/-/g, ' ').slice(0, 38)}</td>
                  <td style={{ fontSize: '0.65rem' }}>{p.post_id?.slice(0, 18) || '--'}</td>
                  <td>{formatDate(p.published_at)}</td>
                  <td>{formatDate(p.last_updated_at)}</td>
                  <td>
                    {p.no_photo && <span className="badge badge-no-photo" style={{ marginRight: 4 }}>NO PHOTO</span>}
                    <span className={`badge ${p.status === 'ACTIVE' ? 'badge-active' : 'badge-sold'}`}>{p.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function EventsTab({ events }) {
  return (
    <div>
      <h2 className="section-title" data-testid="events-title">Events (Supabase live — {(events || []).length} derniers)</h2>
      <div className="card">
        <div className="table-wrap" data-testid="events-full-table">
          <table>
            <thead><tr><th>Date</th><th>Type</th><th>Slug</th><th>Payload</th></tr></thead>
            <tbody>
              {(events || []).map((e, i) => (
                <tr key={e.id || i} data-testid={`event-full-row-${i}`}>
                  <td>{formatDateTime(e.created_at)}</td>
                  <td><EventBadge type={e.type} /></td>
                  <td style={{ fontSize: '0.75rem', maxWidth: 250, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.slug}</td>
                  <td style={{ fontSize: '0.7rem', maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>
                    {e.payload ? JSON.stringify(e.payload).slice(0, 80) : '--'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function ArchitectureTab({ architecture }) {
  if (!architecture) return null;
  const typeClass = { core: 'core', external: 'external', storage: 'storage' };
  return (
    <div>
      <h2 className="section-title" data-testid="arch-title">Architecture Kenbot</h2>
      <div className="section-subtitle">Machine d'etat vehicule</div>
      <div className="states-row" data-testid="states-row">
        <div className="state-box new">NEW</div>
        <div className="state-box sold">SOLD</div>
        <div className="state-box restore">RESTORE</div>
        <div className="state-box price">PRICE_CHANGED</div>
        <div className="state-box photos">PHOTOS_ADDED</div>
      </div>
      <div className="section-subtitle" style={{ marginTop: '2rem' }}>Composants du systeme</div>
      <div className="arch-grid" data-testid="arch-grid">
        {architecture.components.map(c => (
          <div key={c.id} className={`arch-node ${typeClass[c.type] || ''}`} data-testid={`arch-node-${c.id}`}>
            <div className="arch-node-title">{c.name}</div>
            <div className="arch-node-desc">{c.description}</div>
          </div>
        ))}
      </div>
      <div className="card" style={{ marginTop: '1.5rem' }}>
        <div className="section-subtitle">Flux de donnees</div>
        {architecture.flows.map((f, i) => (
          <div className="arch-flow" key={i} data-testid={`flow-${i}`}>
            <span style={{ fontWeight: 600 }}>{f.from}</span>
            <span className="arch-arrow">&rarr;</span>
            <span style={{ fontWeight: 600 }}>{f.to}</span>
            <span style={{ marginLeft: 'auto' }}>{f.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ChangelogTab({ changelog }) {
  return (
    <div>
      <h2 className="section-title" data-testid="changelog-title">Changelog & Fixes</h2>
      {(changelog || []).map((entry, i) => (
        <div className="changelog-item animate-in" key={i} style={{ animationDelay: `${i * 0.05}s` }} data-testid={`changelog-entry-${i}`}>
          <div className="changelog-header">
            <span className="changelog-version">{entry.version}</span>
            <span className="changelog-date">{entry.date}</span>
            <span className={`badge ${entry.type === 'bugfix' ? 'badge-error' : 'badge-info'}`}>{entry.type}</span>
            <span className="changelog-title">{entry.title}</span>
          </div>
          <div className="changelog-changes">
            {(entry.changes || []).map((c, j) => (
              <div className="changelog-change" key={j} data-testid={`change-${i}-${j}`}>
                <span className={`badge badge-${c.severity}`}>{c.severity}</span>
                <span className="changelog-change-desc">
                  {c.description}
                  {c.fix && <><br /><strong style={{ color: 'var(--accent-green)' }}>Fix:</strong> {c.fix}</>}
                </span>
                <span className="changelog-change-file">{c.file}{c.line ? ` L${c.line}` : ''}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function TextPreviewTab({ inventory, onSelectStock, selectedStock }) {
  const [search, setSearch] = useState('');
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState(null);
  const [copied, setCopied] = useState(false);
  const [genCount, setGenCount] = useState(0);

  const activeVehicles = (inventory || []).filter(v => v.status === 'ACTIVE');
  const filtered = activeVehicles.filter(v => {
    if (!search) return true;
    const s = search.toLowerCase();
    return (v.title || '').toLowerCase().includes(s)
      || (v.stock || '').toLowerCase().includes(s)
      || (v.vin || '').toLowerCase().includes(s);
  });

  const handleGenerate = async (stock) => {
    if (!stock) return;
    setGenerating(true);
    setResult(null);
    setCopied(false);
    try {
      const res = await fetch(`${API}/api/generate-text/${stock}`, { method: 'POST' });
      const data = await res.json();
      setResult(data);
      setGenCount(c => c + 1);
    } catch (e) {
      setResult({ ok: false, error: e.message });
    }
    setGenerating(false);
  };

  const handleSelect = (stock) => {
    onSelectStock(stock);
    setResult(null);
    setCopied(false);
  };

  const handleCopy = () => {
    if (result?.text) {
      navigator.clipboard.writeText(result.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const intel = result?.intelligence || {};
  const selectedVehicle = activeVehicles.find(v => v.stock === selectedStock);
  // Pre-fill basic info from inventory when no AI result yet
  const displayKm = intel.km_formatted || (selectedVehicle?.km_int ? `${selectedVehicle.km_int.toLocaleString()} km` : '—');
  const displayPrice = intel.price_formatted || (selectedVehicle?.price_int ? `${selectedVehicle.price_int.toLocaleString()} $` : '—');

  return (
    <div data-testid="text-preview-tab">
      <h2 className="section-title" data-testid="text-preview-title">Preview Texte IA</h2>

      <div className="tp-layout">
        {/* Left: Vehicle selector */}
        <div className="tp-sidebar" data-testid="tp-sidebar">
          <div className="tp-search-wrap">
            <input
              className="tp-search"
              type="text"
              placeholder="Rechercher stock, titre, VIN..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              data-testid="tp-search-input"
            />
            <span className="tp-count">{filtered.length} vehicules</span>
          </div>
          <div className="tp-vehicle-list" data-testid="tp-vehicle-list">
            {filtered.map((v, i) => (
              <div
                key={v.stock || i}
                className={`tp-vehicle-item ${selectedStock === v.stock ? 'selected' : ''}`}
                onClick={() => handleSelect(v.stock)}
                data-testid={`tp-vehicle-${v.stock}`}
              >
                <div className="tp-v-stock">{v.stock}</div>
                <div className="tp-v-title">{v.title || v.slug?.replace(/-/g, ' ')}</div>
                <div className="tp-v-meta">
                  <span>{v.price_int ? `${v.price_int.toLocaleString()} $` : '--'}</span>
                  <span>{v.km_int ? `${v.km_int.toLocaleString()} km` : '--'}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Preview panel */}
        <div className="tp-preview" data-testid="tp-preview-panel">
          {!selectedStock ? (
            <div className="tp-empty" data-testid="tp-empty-state">
              <div className="tp-empty-icon">AI</div>
              <div className="tp-empty-title">Selectionnez un vehicule</div>
              <div className="tp-empty-sub">Cliquez sur un vehicule dans la liste pour generer un apercu du texte Facebook IA</div>
            </div>
          ) : (
            <>
              {/* Vehicle header */}
              <div className="tp-vehicle-header" data-testid="tp-vehicle-header">
                <div>
                  <div className="tp-vh-title">{selectedVehicle?.title || selectedStock}</div>
                  <div className="tp-vh-meta">
                    Stock: {selectedStock}
                    {selectedVehicle?.vin && <> &middot; VIN: {selectedVehicle.vin}</>}
                  </div>
                </div>
                <div className="tp-actions">
                  <button
                    className="tp-generate-btn"
                    onClick={() => handleGenerate(selectedStock)}
                    disabled={generating}
                    data-testid="tp-generate-btn"
                  >
                    {generating ? 'GENERATION...' : genCount > 0 && result?.ok ? 'REGENERER' : 'GENERER LE TEXTE'}
                  </button>
                  {result?.ok && (
                    <button className="tp-copy-btn" onClick={handleCopy} data-testid="tp-copy-btn">
                      {copied ? 'COPIE !' : 'COPIER'}
                    </button>
                  )}
                </div>
              </div>

              {/* Intelligence panel */}
              {(result?.intelligence || selectedVehicle) && (
                <div className="tp-intel" data-testid="tp-intel-panel">
                  <div className="tp-intel-title">Intelligence Vehicule</div>
                  <div className="tp-intel-grid">
                    <div className="tp-intel-item">
                      <span className="tp-il">Marque</span>
                      <span className="tp-iv">{intel.brand || '—'}</span>
                    </div>
                    <div className="tp-intel-item">
                      <span className="tp-il">Modele</span>
                      <span className="tp-iv">{intel.model || '—'}</span>
                    </div>
                    <div className="tp-intel-item">
                      <span className="tp-il">Trim</span>
                      <span className="tp-iv">{intel.trim || '—'}</span>
                    </div>
                    <div className="tp-intel-item">
                      <span className="tp-il">Type</span>
                      <span className="tp-iv">
                        <span className={`badge tp-type-badge tp-type-${intel.vehicle_type || 'general'}`}>
                          {intel.vehicle_type || '—'}
                        </span>
                      </span>
                    </div>
                    {intel.hp && (
                      <div className="tp-intel-item">
                        <span className="tp-il">Moteur</span>
                        <span className="tp-iv tp-engine">{intel.engine} — {intel.hp} HP</span>
                      </div>
                    )}
                    {intel.trim_vibe && (
                      <div className="tp-intel-item tp-intel-wide">
                        <span className="tp-il">Vibe</span>
                        <span className="tp-iv tp-vibe">{intel.trim_vibe}</span>
                      </div>
                    )}
                    <div className="tp-intel-item">
                      <span className="tp-il">KM</span>
                      <span className="tp-iv">{displayKm} {intel.km_description && <span className="tp-desc">({intel.km_description})</span>}</span>
                    </div>
                    <div className="tp-intel-item">
                      <span className="tp-il">Prix</span>
                      <span className="tp-iv">{displayPrice} {intel.price_description && <span className="tp-desc">({intel.price_description})</span>}</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Generated text */}
              {generating && (
                <div className="tp-loading" data-testid="tp-loading">
                  <div className="tp-loading-bar"></div>
                  <span>Generation du texte via GPT-4o...</span>
                </div>
              )}

              {result && !generating && (
                result.ok ? (
                  <div className="tp-text-result" data-testid="tp-text-result">
                    <div className="tp-text-header">
                      <span className="tp-text-label">Texte Facebook genere</span>
                      <div className="tp-text-meta">
                        <span className="badge badge-ok">{result.chars} chars</span>
                        <span className="badge badge-info">style: {result.style}</span>
                        <span className="badge badge-active">{result.model}</span>
                      </div>
                    </div>
                    <div className="tp-text-body" data-testid="tp-text-body">
                      {result.text}
                    </div>
                  </div>
                ) : (
                  <div className="tp-error" data-testid="tp-error">
                    <span className="badge badge-error">ERREUR</span>
                    <span>{result.error}</span>
                  </div>
                )
              )}

              {!result && !generating && (
                <div className="tp-hint" data-testid="tp-hint">
                  Cliquez sur "GENERER LE TEXTE" pour voir l'apercu IA
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function RunPanel({ onClose }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [dryRun, setDryRun] = useState(false);
  const [maxTargets, setMaxTargets] = useState(4);
  const [forceStock, setForceStock] = useState('');

  const triggerRun = async () => {
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch(`${API}/api/trigger/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dry_run: dryRun, max_targets: maxTargets, force_stock: forceStock || null }),
      });
      const data = await res.json();
      setResult(data);
    } catch (e) {
      setResult({ ok: false, message: e.message });
    }
    setLoading(false);
  };

  return (
    <div className="run-panel" data-testid="run-panel">
      <div className="run-panel-inner">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <span style={{ fontFamily: 'Chivo, sans-serif', fontWeight: 900, fontSize: '1.1rem' }}>LANCER LE CRON</span>
          <button onClick={onClose} style={{ background: 'none', border: '1px solid var(--border)', padding: '4px 12px', cursor: 'pointer', fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.75rem' }} data-testid="close-run-panel">FERMER</button>
        </div>

        <div className="run-options">
          <label className="run-option" data-testid="dry-run-toggle">
            <input type="checkbox" checked={dryRun} onChange={e => setDryRun(e.target.checked)} />
            <span>Dry Run</span>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>— Simule sans publier</span>
          </label>

          <div className="run-option">
            <span>Max targets</span>
            <input type="number" value={maxTargets} onChange={e => setMaxTargets(parseInt(e.target.value) || 4)} min={1} max={20} style={{ width: 60, fontFamily: 'IBM Plex Mono', padding: '4px 8px', border: '1px solid var(--border)' }} data-testid="max-targets-input" />
          </div>

          <div className="run-option">
            <span>Force stock</span>
            <input type="text" value={forceStock} onChange={e => setForceStock(e.target.value)} placeholder="ex: 06234" style={{ width: 120, fontFamily: 'IBM Plex Mono', padding: '4px 8px', border: '1px solid var(--border)', textTransform: 'uppercase' }} data-testid="force-stock-input" />
            <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>— Optionnel</span>
          </div>
        </div>

        <button className="run-execute-btn" onClick={triggerRun} disabled={loading} data-testid="execute-run-btn">
          {loading ? 'ENVOI EN COURS...' : 'EXECUTER'}
        </button>

        {result && (
          <div className={`run-result ${result.ok ? 'run-result-ok' : 'run-result-error'}`} data-testid="run-result">
            <span style={{ fontWeight: 600 }}>{result.ok ? 'OK' : 'ERREUR'}</span>
            <span>{result.message}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function formatTime(ts) {
  if (!ts) return '--';
  try { return new Date(ts).toLocaleTimeString('fr-CA', { hour: '2-digit', minute: '2-digit' }); } catch { return ts; }
}
function formatDate(ts) {
  if (!ts) return '--';
  try { return new Date(ts).toLocaleDateString('fr-CA', { month: 'short', day: 'numeric', year: 'numeric' }); } catch { return ts; }
}
function formatDateTime(ts) {
  if (!ts) return '--';
  try { const d = new Date(ts); return `${d.toLocaleDateString('fr-CA', { month: 'short', day: 'numeric' })} ${d.toLocaleTimeString('fr-CA', { hour: '2-digit', minute: '2-digit' })}`; } catch { return ts; }
}

export default App;
