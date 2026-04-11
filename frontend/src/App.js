import React, { useState, useEffect, useCallback } from 'react';
import './App.css';

const API = process.env.REACT_APP_BACKEND_URL;

function App() {
  const [tab, setTab] = useState('dashboard');
  const [status, setStatus] = useState(null);
  const [runs, setRuns] = useState([]);
  const [inventory, setInventory] = useState([]);
  const [posts, setPosts] = useState([]);
  const [changelog, setChangelog] = useState([]);
  const [architecture, setArchitecture] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [statusRes, runsRes, invRes, postsRes, changelogRes, archRes] = await Promise.all([
        fetch(`${API}/api/system/status`),
        fetch(`${API}/api/cron/runs`),
        fetch(`${API}/api/inventory`),
        fetch(`${API}/api/posts`),
        fetch(`${API}/api/changelog`),
        fetch(`${API}/api/architecture`),
      ]);
      setStatus(await statusRes.json());
      setRuns(await runsRes.json());
      setInventory(await invRes.json());
      setPosts(await postsRes.json());
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
            {tab === 'dashboard' && <DashboardTab status={status} runs={runs} posts={posts} />}
            {tab === 'inventory' && <InventoryTab inventory={inventory} />}
            {tab === 'posts' && <PostsTab posts={posts} />}
            {tab === 'architecture' && <ArchitectureTab architecture={architecture} />}
            {tab === 'changelog' && <ChangelogTab changelog={changelog} />}
          </>
        )}
      </div>
    </div>
  );
}

function Header({ tab, setTab, status }) {
  const tabs = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'inventory', label: 'Inventaire' },
    { id: 'posts', label: 'Posts FB' },
    { id: 'architecture', label: 'Architecture' },
    { id: 'changelog', label: 'Changelog' },
  ];
  return (
    <header className="header" data-testid="header">
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <span className="header-logo" data-testid="header-logo">KENBOT</span>
        <span className="status-dot" data-testid="status-dot" />
      </div>
      <nav className="header-nav" data-testid="header-nav">
        {tabs.map(t => (
          <button
            key={t.id}
            className={tab === t.id ? 'active' : ''}
            onClick={() => setTab(t.id)}
            data-testid={`nav-${t.id}`}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <div className="header-right">
        <span className="version-tag" data-testid="version-tag">v{status?.version || '2.1.0'}</span>
      </div>
    </header>
  );
}

function LoadingState() {
  return (
    <div style={{ textAlign: 'center', padding: '4rem', fontFamily: 'IBM Plex Mono, monospace', color: 'var(--text-secondary)' }}>
      <div style={{ fontSize: '1.5rem', marginBottom: '1rem' }}>[ LOADING ]</div>
      <div>Chargement des donnees...</div>
    </div>
  );
}

function DashboardTab({ status, runs, posts }) {
  const stats = status?.stats || {};
  const inv = stats.inventory || {};
  const postStats = stats.posts || {};
  const lastRun = status?.last_run;

  return (
    <div>
      <div className="stats-grid animate-in" data-testid="stats-grid">
        <div className="card animate-in delay-1">
          <div className="card-label">Vehicules actifs</div>
          <div className="card-value" data-testid="stat-active-vehicles">{inv.active || 0}</div>
          <div className="card-sub">{inv.sold || 0} vendus</div>
        </div>
        <div className="card animate-in delay-2">
          <div className="card-label">Posts Facebook</div>
          <div className="card-value" data-testid="stat-active-posts">{postStats.active || 0}</div>
          <div className="card-sub">{postStats.with_photos || 0} avec photos</div>
        </div>
        <div className="card animate-in delay-3">
          <div className="card-label">Sans photos</div>
          <div className="card-value" data-testid="stat-no-photo" style={{ color: postStats.no_photo > 0 ? 'var(--accent-red)' : 'inherit' }}>
            {postStats.no_photo || 0}
          </div>
          <div className="card-sub">a mettre a jour</div>
        </div>
        <div className="card animate-in delay-4">
          <div className="card-label">Dernier run</div>
          <div className="card-value small" data-testid="stat-last-run">
            {lastRun ? formatTime(lastRun.timestamp) : '--:--'}
          </div>
          <div className="card-sub">
            {lastRun && <span className={`badge ${lastRun.status === 'OK' ? 'badge-ok' : 'badge-error'}`}>{lastRun.status}</span>}
          </div>
        </div>
      </div>

      <div className="bento-grid">
        <div className="card animate-in">
          <div className="section-subtitle">Runs recents</div>
          <CronRunsTable runs={runs} />
        </div>
        <div className="card animate-in">
          <div className="section-subtitle">Posts Status</div>
          <PostsMiniList posts={posts} />
        </div>
      </div>
    </div>
  );
}

function CronRunsTable({ runs }) {
  return (
    <div className="table-wrap" data-testid="cron-runs-table">
      <table>
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Status</th>
            <th>Inv</th>
            <th>New</th>
            <th>Sold</th>
            <th>Price</th>
            <th>Photos</th>
            <th>Posted</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r, i) => (
            <tr key={r.id || i} data-testid={`run-row-${i}`}>
              <td>{formatTime(r.timestamp)}</td>
              <td><span className={`badge ${r.status === 'OK' ? 'badge-ok' : 'badge-error'}`}>{r.status}</span></td>
              <td>{r.inv_count}</td>
              <td>{r.new_count > 0 ? <span style={{ color: 'var(--accent-green)', fontWeight: 600 }}>+{r.new_count}</span> : '0'}</td>
              <td>{r.sold_count > 0 ? <span style={{ color: 'var(--accent-red)', fontWeight: 600 }}>{r.sold_count}</span> : '0'}</td>
              <td>{r.price_changed > 0 ? <span style={{ color: '#B45309', fontWeight: 600 }}>{r.price_changed}</span> : '0'}</td>
              <td>{r.photos_added > 0 ? <span style={{ color: '#7C3AED', fontWeight: 600 }}>{r.photos_added}</span> : '0'}</td>
              <td>{r.posted}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PostsMiniList({ posts }) {
  const sorted = [...posts].sort((a, b) => (a.no_photo === b.no_photo ? 0 : a.no_photo ? -1 : 1));
  return (
    <div data-testid="posts-mini-list">
      {sorted.map((p, i) => (
        <div className="post-item" key={p.slug || i} data-testid={`post-item-${i}`}>
          <span className="post-stock">{p.stock}</span>
          <span className="post-title">{p.slug?.replace(/-/g, ' ').slice(0, 40)}</span>
          {p.no_photo ? (
            <span className="badge badge-no-photo">NO PHOTO</span>
          ) : (
            <span className="post-photos">{p.photo_count || 0} photos</span>
          )}
          <span className={`badge ${p.status === 'ACTIVE' ? 'badge-active' : 'badge-sold'}`}>{p.status}</span>
        </div>
      ))}
    </div>
  );
}

function InventoryTab({ inventory }) {
  const active = inventory.filter(v => v.status === 'ACTIVE');
  const sold = inventory.filter(v => v.status === 'SOLD');
  return (
    <div>
      <h2 className="section-title" data-testid="inventory-title">Inventaire</h2>
      <div className="stats-grid" style={{ marginBottom: '1.5rem' }}>
        <div className="card">
          <div className="card-label">Total</div>
          <div className="card-value">{inventory.length}</div>
        </div>
        <div className="card">
          <div className="card-label">Actifs</div>
          <div className="card-value" style={{ color: 'var(--accent-green)' }}>{active.length}</div>
        </div>
        <div className="card">
          <div className="card-label">Vendus</div>
          <div className="card-value">{sold.length}</div>
        </div>
        <div className="card">
          <div className="card-label">Sans photo</div>
          <div className="card-value" style={{ color: 'var(--accent-red)' }}>{inventory.filter(v => v.no_photo).length}</div>
        </div>
      </div>
      <div className="card">
        <div className="table-wrap" data-testid="inventory-table">
          <table>
            <thead>
              <tr>
                <th>Stock</th>
                <th>Titre</th>
                <th>Prix</th>
                <th>KM</th>
                <th>VIN</th>
                <th>Photos</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {inventory.map((v, i) => (
                <tr key={v.slug || i} data-testid={`inv-row-${i}`}>
                  <td style={{ fontWeight: 600 }}>{v.stock}</td>
                  <td style={{ fontFamily: 'IBM Plex Sans, sans-serif' }}>{v.title}</td>
                  <td>{v.price || (v.price_int ? `${v.price_int.toLocaleString()} $` : '--')}</td>
                  <td>{v.mileage || (v.km_int ? `${v.km_int.toLocaleString()} km` : '--')}</td>
                  <td style={{ fontSize: '0.7rem' }}>{v.vin || '--'}</td>
                  <td>
                    {v.no_photo ? <span className="badge badge-no-photo">0</span> : v.photo_count || '--'}
                  </td>
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
  const noPhoto = posts.filter(p => p.no_photo);
  const withPhotos = posts.filter(p => !p.no_photo && p.status === 'ACTIVE');
  return (
    <div>
      <h2 className="section-title" data-testid="posts-title">Posts Facebook</h2>
      {noPhoto.length > 0 && (
        <div className="card" style={{ borderColor: 'var(--accent-red)', marginBottom: '1.5rem' }}>
          <div className="section-subtitle" style={{ color: 'var(--accent-red)' }}>
            Posts sans photos ({noPhoto.length}) — En attente de PHOTOS_ADDED
          </div>
          {noPhoto.map((p, i) => (
            <div className="post-item" key={p.slug || i} data-testid={`no-photo-post-${i}`}>
              <span className="post-stock">{p.stock}</span>
              <span className="post-title">{p.slug?.replace(/-/g, ' ')}</span>
              <span className="badge badge-no-photo">NO PHOTO</span>
              <span style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.7rem', color: 'var(--text-secondary)' }}>
                {p.post_id?.slice(0, 12)}...
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="card">
        <div className="section-subtitle">Posts avec photos ({withPhotos.length})</div>
        <div className="table-wrap" data-testid="posts-table">
          <table>
            <thead>
              <tr>
                <th>Stock</th>
                <th>Slug</th>
                <th>Post ID</th>
                <th>Photos</th>
                <th>Publie le</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {posts.map((p, i) => (
                <tr key={p.slug || i} data-testid={`post-row-${i}`}>
                  <td style={{ fontWeight: 600 }}>{p.stock}</td>
                  <td style={{ fontFamily: 'IBM Plex Sans, sans-serif', fontSize: '0.8rem' }}>{p.slug?.replace(/-/g, ' ').slice(0, 35)}</td>
                  <td style={{ fontSize: '0.7rem' }}>{p.post_id?.slice(0, 15) || '--'}</td>
                  <td>{p.no_photo ? <span className="badge badge-no-photo">0</span> : p.photo_count}</td>
                  <td>{p.published_at ? formatDate(p.published_at) : '--'}</td>
                  <td><span className={`badge ${p.status === 'ACTIVE' ? 'badge-active' : 'badge-sold'}`}>{p.status}</span></td>
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
  const types = { core: 'core', external: 'external', storage: 'storage', module: '', service: '', output: '' };
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
          <div key={c.id} className={`arch-node ${types[c.type] || ''}`} data-testid={`arch-node-${c.id}`}>
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
      {changelog.map((entry, i) => (
        <div className="changelog-item animate-in" key={i} style={{ animationDelay: `${i * 0.05}s` }} data-testid={`changelog-entry-${i}`}>
          <div className="changelog-header">
            <span className="changelog-version">{entry.version}</span>
            <span className="changelog-date">{entry.date}</span>
            <span className={`badge ${entry.type === 'bugfix' ? 'badge-error' : 'badge-info'}`}>{entry.type}</span>
            <span className="changelog-title">{entry.title}</span>
          </div>
          <div className="changelog-changes">
            {entry.changes.map((c, j) => (
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

// ─── Helpers ───
function formatTime(ts) {
  if (!ts) return '--';
  try {
    const d = new Date(ts);
    return d.toLocaleTimeString('fr-CA', { hour: '2-digit', minute: '2-digit' });
  } catch { return ts; }
}

function formatDate(ts) {
  if (!ts) return '--';
  try {
    const d = new Date(ts);
    return d.toLocaleDateString('fr-CA', { month: 'short', day: 'numeric' });
  } catch { return ts; }
}

export default App;
