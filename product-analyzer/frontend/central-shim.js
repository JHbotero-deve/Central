/* Si /opportunities/top exige sesion (401), el inicio usa el catalogo publico ordenado por puntuacion. */
(()=>{
  const orig = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const res = await orig(input, init);
    const url = typeof input === 'string' ? input : ((input && input.url) || '');
    const m = url.match(/\/api\/v1\/opportunities\/top(\?.*)?$/);
    if (m && res.status === 401) {
      try {
        const lim = Number(new URLSearchParams((m[1] || '').slice(1)).get('limit')) || 12;
        const r2 = await orig('/api/v1/products?limit=50', { cache: 'no-store', headers: { Accept: 'application/json' } });
        if (r2.ok) {
          const data = await r2.json();
          const list = (Array.isArray(data) ? data : (data.items || data.products || [])).slice()
            .sort((a, b) => (Number(b.opportunity_score) || 0) - (Number(a.opportunity_score) || 0)).slice(0, lim);
          return new Response(JSON.stringify(list), { status: 200, headers: { 'Content-Type': 'application/json' } });
        }
      } catch (e) { /* si falla, devuelve el 401 original */ }
    }
    return res;
  };
})();