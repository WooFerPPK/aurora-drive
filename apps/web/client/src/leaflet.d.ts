// Minimal ambient declaration for Leaflet. The real types ship as
// @types/leaflet on DefinitelyTyped, but this project doesn't depend on
// them and the surface used here (markers, polylines, divIcon, CRS
// hooks) is well-trodden — typing it as `any` matches the JS that this
// module was converted from. Replace with a proper dep when a widget
// needs real Leaflet type safety.
declare module 'leaflet' {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const L: any
  export default L
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  export const Point: any
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  export const Bounds: any
}
declare module 'leaflet/dist/leaflet.css'
