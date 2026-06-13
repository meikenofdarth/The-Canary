'use client';

export function Header() {
  return (
    <header
      className="flex items-center gap-2.5 px-6 py-4 border-b"
      style={{ borderColor: '#F0E6D3', backgroundColor: 'transparent' }}
    >
      {/* Small bird silhouette */}
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
        <path
          d="M12 2C8 2 5 5 5 8c0 2 1 3.5 2.5 4.5L6 18c0 1 .5 2 1.5 2.5L9 22h6l1.5-1.5C17.5 20 18 19 18 18l-1.5-5.5C18 11.5 19 10 19 8c0-3-3-6-7-6zm-1 6a1 1 0 1 1 0-2 1 1 0 0 1 0 2z"
          fill="#FFD700"
          stroke="#F5C842"
          strokeWidth="0.5"
        />
      </svg>
      <h1 className="text-xl font-semibold" style={{ color: '#2D2D2D' }}>
        Canary
      </h1>
    </header>
  );
}
