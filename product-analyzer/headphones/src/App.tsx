import { motion } from "motion/react";
import { ExternalLink, RefreshCw, ShoppingBag } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type Publication = {
  id: number | string;
  product_id?: number | string;
  title: string;
  subtitle?: string;
  description?: string;
  price_display?: string;
  sale_price?: number | null;
  current_price?: number | null;
  currency?: string;
  image_url?: string | null;
  image_gallery?: string[];
  product_url?: string | null;
  affiliate_url?: string | null;
  platform?: string;
  category?: string;
  opportunity_score?: number | null;
  checkout_mode?: string;
};

const API = "/api";

const money = (value?: number | null, currency = "COP") => {
  if (value == null || !Number.isFinite(Number(value))) return "Consultar";
  const normalized = String(currency).toUpperCase();
  return new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency: normalized === "USD" ? "USD" : "COP",
    maximumFractionDigits: 0,
  }).format(Number(value));
};

const priceOf = (product: Publication) =>
  product.price_display || money(product.sale_price ?? product.current_price, product.currency);

const imageOf = (product: Publication) =>
  product.image_url || product.image_gallery?.find(Boolean) || "";

const hrefOf = (product: Publication) =>
  product.product_url || product.affiliate_url || "";

const categoryOf = (product: Publication) =>
  product.category || product.platform || "Producto";

function ProductCard({ product }: { product: Publication }) {
  const [rotation, setRotation] = useState({ x: 0, y: 0 });
  const image = imageOf(product);
  const href = hrefOf(product);

  return (
    <motion.article
      className="group relative overflow-hidden rounded-[28px] border border-white/10 bg-white/[0.045] p-3 shadow-2xl shadow-black/30 [perspective:1200px]"
      whileHover={{ y: -5 }}
      onPointerMove={(event) => {
        const rect = event.currentTarget.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width - 0.5;
        const y = (event.clientY - rect.top) / rect.height - 0.5;
        setRotation({ x: y * -9, y: x * 12 });
      }}
      onPointerLeave={() => setRotation({ x: 0, y: 0 })}
    >
      <div
        className="relative aspect-[1/1.08] overflow-hidden rounded-[22px] border border-white/10 bg-[radial-gradient(circle_at_50%_35%,rgba(255,138,0,.18),transparent_35%),linear-gradient(145deg,#1a1f27,#080a0e)] transition-transform duration-150"
        style={{
          transform: `rotateX(${rotation.x}deg) rotateY(${rotation.y}deg)`,
          transformStyle: "preserve-3d",
          boxShadow: "0 30px 70px rgba(0,0,0,.35)",
        }}
      >
        {image ? (
          <img
            src={image}
            alt={product.title}
            className="absolute inset-0 h-full w-full object-contain p-8 transition-transform duration-300 group-hover:scale-[1.04]"
            loading="lazy"
            referrerPolicy="no-referrer"
          />
        ) : (
          <div className="grid h-full place-items-center text-xs uppercase tracking-[0.18em] text-white/35">
            Imagen no disponible
          </div>
        )}
        <div className="absolute inset-x-4 top-4 flex items-center justify-between gap-2">
          <span className="rounded-full border border-white/10 bg-black/55 px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-white/65">
            {product.platform || "Central"}
          </span>
          {product.opportunity_score != null && (
            <span className="rounded-full bg-orange-500 px-3 py-1 text-[10px] font-black text-black">
              {Math.round(Number(product.opportunity_score))}/100
            </span>
          )}
        </div>
      </div>

      <div className="px-2 pb-2 pt-4">
        <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-orange-400">
          {categoryOf(product)}
        </p>
        <h2 className="line-clamp-2 min-h-12 text-xl font-bold tracking-tight text-white">
          {product.title}
        </h2>
        <p className="mt-2 line-clamp-2 min-h-10 text-xs leading-5 text-white/45">
          {product.subtitle || product.description || "Producto publicado en Central."}
        </p>
        <div className="mt-4 flex items-center justify-between gap-3">
          <strong className="text-lg font-black text-white">{priceOf(product)}</strong>
          {href ? (
            <a
              href={href}
              target="_blank"
              rel="nofollow sponsored noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-full bg-orange-500 px-4 py-2.5 text-xs font-black text-black transition hover:bg-orange-400"
            >
              Ver producto
              <ExternalLink size={13} />
            </a>
          ) : (
            <span className="rounded-full border border-white/10 px-4 py-2.5 text-xs font-bold text-white/45">
              Sin enlace
            </span>
          )}
        </div>
      </div>
    </motion.article>
  );
}

export default function App() {
  const [products, setProducts] = useState<Publication[]>([]);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API}/publications?limit=100`, {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const items = Array.isArray(data)
        ? data
        : Array.isArray(data.items)
          ? data.items
          : Array.isArray(data.publications)
            ? data.publications
            : Array.isArray(data.data)
              ? data.data
              : [];
      setProducts(items);
    } catch (cause) {
      setProducts([]);
      setError(cause instanceof Error ? cause.message : "No se pudo cargar el catálogo");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const categories = useMemo(
    () => [...new Set(products.map((product) => product.category).filter(Boolean))].sort(),
    [products],
  );

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return products.filter((product) => {
      const matchesQuery =
        !normalized ||
        [product.title, product.subtitle, product.category, product.platform]
          .some((value) => String(value || "").toLowerCase().includes(normalized));
      return matchesQuery && (!category || product.category === category);
    });
  }, [products, query, category]);

  return (
    <main className="min-h-screen overflow-x-hidden bg-[#050607] text-white">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_50%_-10%,rgba(255,138,0,.16),transparent_32%),radial-gradient(circle_at_90%_25%,rgba(255,90,31,.08),transparent_28%)]" />

      <header className="sticky top-0 z-40 border-b border-white/10 bg-[#050607]/80 backdrop-blur-xl">
        <div className="mx-auto flex min-h-16 w-[min(1380px,calc(100%-32px))] items-center justify-between gap-4">
          <a href="/tienda" className="flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-xl bg-orange-500 text-lg font-black text-black">C</span>
            <span>
              <strong className="block text-sm font-black tracking-[0.13em]">CENTRAL</strong>
              <small className="block text-[9px] uppercase tracking-[0.16em] text-white/35">3D Showcase</small>
            </span>
          </a>
          <div className="flex items-center gap-2">
            <a href="/tienda" className="rounded-full border border-white/10 px-4 py-2 text-[11px] font-bold text-white/65 hover:text-white">
              Tienda
            </a>
            <button
              type="button"
              onClick={load}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-[11px] font-black text-black disabled:opacity-50"
            >
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
              Actualizar
            </button>
          </div>
        </div>
      </header>

      <section className="relative mx-auto w-[min(1380px,calc(100%-32px))] pb-10 pt-16">
        <div className="max-w-3xl">
          <p className="text-[10px] font-black uppercase tracking-[0.2em] text-orange-400">Central · catálogo publicado</p>
          <h1 className="mt-4 text-5xl font-black tracking-[-0.06em] sm:text-7xl">
            Productos reales.
            <span className="block text-white/30">Presentación 3D.</span>
          </h1>
          <p className="mt-6 max-w-2xl text-sm leading-6 text-white/50">
            Esta vista consume las publicaciones reales de Central. El editor vive en un solo lugar; aquí solo se muestra el resultado publicado.
          </p>
        </div>

        <div className="mt-8 flex flex-col gap-3 sm:flex-row">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar producto..."
            className="h-12 flex-1 rounded-full border border-white/10 bg-white/[0.05] px-5 text-sm text-white outline-none placeholder:text-white/30 focus:border-orange-500/50"
          />
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            className="h-12 rounded-full border border-white/10 bg-[#11151b] px-5 text-sm text-white outline-none focus:border-orange-500/50"
          >
            <option value="">Todas las categorías</option>
            {categories.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <div className="inline-flex h-12 items-center justify-center gap-2 rounded-full border border-white/10 px-5 text-xs font-bold text-white/45">
            <ShoppingBag size={14} />
            {filtered.length} productos
          </div>
        </div>
      </section>

      <section className="relative mx-auto grid w-[min(1380px,calc(100%-32px))] grid-cols-1 gap-5 pb-20 sm:grid-cols-2 lg:grid-cols-3">
        {loading && (
          <div className="col-span-full rounded-3xl border border-white/10 p-16 text-center text-sm text-white/40">
            Cargando publicaciones...
          </div>
        )}
        {!loading && error && (
          <div className="col-span-full rounded-3xl border border-red-400/20 bg-red-400/5 p-16 text-center">
            <p className="text-sm font-bold text-white">No se pudo cargar el catálogo.</p>
            <p className="mt-2 text-xs text-white/40">{error}</p>
          </div>
        )}
        {!loading && !error && !filtered.length && (
          <div className="col-span-full rounded-3xl border border-dashed border-white/15 p-16 text-center">
            <p className="text-lg font-bold text-white/70">No hay publicaciones.</p>
            <p className="mt-2 text-xs text-white/35">Publica productos desde el editor de Central.</p>
          </div>
        )}
        {!loading && !error && filtered.map((product) => (
          <ProductCard key={String(product.id)} product={product} />
        ))}
      </section>
    </main>
  );
}
