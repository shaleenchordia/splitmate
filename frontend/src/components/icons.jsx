// Minimal inline icon set (lucide-style paths) so the UI gets crisp icons
// without a dependency. Size/color follow the surrounding text.

const base = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
}

export function Icon({ d, size = 15, style }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} {...base} style={{ flexShrink: 0, verticalAlign: '-2px', ...style }}>
      {Array.isArray(d) ? d.map((p, i) => <path key={i} d={p} />) : <path d={d} />}
    </svg>
  )
}

export const paths = {
  calendar: ['M8 2v4M16 2v4', 'M3 6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z', 'M3 10h18'],
  coins: ['M12 1v22', 'M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6'],
  trend: ['M22 7l-8.5 8.5-5-5L2 17', 'M16 7h6v6'],
  users: ['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2', 'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8', 'M22 21v-2a4 4 0 0 0-3-3.87', 'M16 3.13a4 4 0 0 1 0 7.75'],
  sparkle: ['M12 3l1.9 5.7a2 2 0 0 0 1.3 1.3L21 12l-5.8 1.9a2 2 0 0 0-1.3 1.3L12 21l-1.9-5.8a2 2 0 0 0-1.3-1.3L3 12l5.8-1.9a2 2 0 0 0 1.3-1.3z'],
  receipt: ['M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1z', 'M8 7h8M8 11h8M12 15h4'],
  chart: ['M3 3v16a2 2 0 0 0 2 2h16', 'M7 13v4M12 9v8M17 5v12'],
  sun: ['M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10', 'M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4'],
  moon: ['M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8'],
  trash: ['M3 6h18', 'M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6', 'M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2', 'M10 11v6M14 11v6'],
  pencil: ['M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z'],
  plus: ['M5 12h14M12 5v14'],
  upload: ['M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4', 'M17 8l-5-5-5 5', 'M12 3v12'],
  camera: ['M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3z', 'M12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8'],
  check: ['M20 6L9 17l-5-5'],
  x: ['M18 6L6 18M6 6l12 12'],
  arrowLeft: ['M19 12H5', 'M12 19l-7-7 7-7'],
  arrowRight: ['M5 12h14', 'M12 5l7 7-7 7'],
  wallet: ['M21 12V7H5a2 2 0 0 1 0-4h14v4', 'M3 5v14a2 2 0 0 0 2 2h16v-5', 'M18 12a2 2 0 0 0 0 4h4v-4z'],
  logout: ['M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4', 'M16 17l5-5-5-5', 'M21 12H9'],
  alert: ['M12 9v4M12 17h.01', 'M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z'],
  bot: ['M12 8V4H8', 'M4 8h16a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2z', 'M9 13h.01M15 13h.01'],
}

export const Calendar = (p) => <Icon d={paths.calendar} {...p} />
export const Coins = (p) => <Icon d={paths.coins} {...p} />
export const Trend = (p) => <Icon d={paths.trend} {...p} />
export const Users = (p) => <Icon d={paths.users} {...p} />
export const Sparkle = (p) => <Icon d={paths.sparkle} {...p} />
export const Receipt = (p) => <Icon d={paths.receipt} {...p} />
export const Chart = (p) => <Icon d={paths.chart} {...p} />
export const Sun = (p) => <Icon d={paths.sun} {...p} />
export const Moon = (p) => <Icon d={paths.moon} {...p} />
export const Trash = (p) => <Icon d={paths.trash} {...p} />
export const Pencil = (p) => <Icon d={paths.pencil} {...p} />
export const Plus = (p) => <Icon d={paths.plus} {...p} />
export const Upload = (p) => <Icon d={paths.upload} {...p} />
export const Camera = (p) => <Icon d={paths.camera} {...p} />
export const Check = (p) => <Icon d={paths.check} {...p} />
export const X = (p) => <Icon d={paths.x} {...p} />
export const ArrowLeft = (p) => <Icon d={paths.arrowLeft} {...p} />
export const ArrowRight = (p) => <Icon d={paths.arrowRight} {...p} />
export const Wallet = (p) => <Icon d={paths.wallet} {...p} />
export const Logout = (p) => <Icon d={paths.logout} {...p} />
export const Alert = (p) => <Icon d={paths.alert} {...p} />
export const Bot = (p) => <Icon d={paths.bot} {...p} />

// Deterministic avatar hue per name, shared by every avatar in the app.
export function Avatar({ name, size = 26 }) {
  let h = 0
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 360
  return (
    <span
      className="avatar"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.42,
        background: `hsl(${h} 65% 88%)`,
        color: `hsl(${h} 55% 30%)`,
      }}
    >
      {name.trim().slice(0, 1).toUpperCase()}
      {(name.trim().split(/\s+/)[1] || '').slice(0, 1).toUpperCase()}
    </span>
  )
}
