// backend/tests/golden/gen_golden.mjs
//
// Genera la GOLDEN del motor de proyección: corre la función simular() REAL del
// artefacto de referencia (docs/modelo/referencia/Dashboard_Artefacto.jsx) — la
// fuente de verdad que el motor Python (C7) dice replicar — y vuelca su salida
// mensual a JSON. NO reescribe la lógica: extrae el texto verbatim de simular() y
// sus dependencias de módulo del JSX y las evalúa. Cero transcripción a mano.
//
// Escenario: paramétrico PURO — simular(p_default, [], {}) — sin eventos manuales
// (deuda/crédito/DIAN) ni overrides, para aislar la MATEMÁTICA del motor. El IVA del
// artefacto era solo el evento DIAN manual: al pasar eventos=[] queda fuera, igual
// que en el motor Python (paridad justa; el IVA es PR-2, en ambos lados).
//
// Uso:  node backend/tests/golden/gen_golden.mjs [ruta_jsx] > golden_simular.json

import fs from "node:fs";

const JSX =
  process.argv[2] || "docs/modelo/referencia/Dashboard_Artefacto.jsx";
const src = fs.readFileSync(JSX, "utf8");

// Extrae el texto balanceado de un bloque abierto por `open` a partir de un ancla
// textual (p. ej. "function simular"): incluye desde el ancla hasta el `close` que
// cierra el primer `open` tras el ancla.
function bloque(texto, ancla, open, close) {
  const start = texto.indexOf(ancla);
  if (start < 0) throw new Error(`no encontrado: ${ancla}`);
  const openIdx = texto.indexOf(open, start);
  let depth = 0;
  for (let j = openIdx; j < texto.length; j++) {
    if (texto[j] === open) depth++;
    else if (texto[j] === close) {
      depth--;
      if (depth === 0) return texto.slice(start, j + 1);
    }
  }
  throw new Error(`desbalanceado desde ${ancla}`);
}

// Una sentencia de una sola línea terminada en `;` a partir de un ancla.
function linea(texto, ancla) {
  const start = texto.indexOf(ancla);
  if (start < 0) throw new Error(`no encontrado: ${ancla}`);
  const end = texto.indexOf(";", start);
  return texto.slice(start, end + 1);
}

// Extrae una `function nombre(...) { ... }` completa. Balancea primero los
// PARÉNTESIS de la lista de parámetros (que puede contener `{}`, p. ej.
// `overrides = {}`) y solo después balancea las LLAVES del cuerpo. Sin esto, el
// `{}` de un parámetro por defecto trunca la extracción en la firma.
function funcion(texto, ancla) {
  const start = texto.indexOf(ancla);
  if (start < 0) throw new Error(`no encontrado: ${ancla}`);
  const parenOpen = texto.indexOf("(", start);
  let d = 0,
    i = parenOpen;
  for (; i < texto.length; i++) {
    if (texto[i] === "(") d++;
    else if (texto[i] === ")") {
      d--;
      if (d === 0) break;
    }
  }
  const braceOpen = texto.indexOf("{", i);
  let b = 0;
  for (let j = braceOpen; j < texto.length; j++) {
    if (texto[j] === "{") b++;
    else if (texto[j] === "}") {
      b--;
      if (b === 0) return texto.slice(start, j + 1);
    }
  }
  throw new Error(`función desbalanceada desde ${ancla}`);
}

const MESES = linea(src, "const MESES =");
const MS_DIA = linea(src, "const MS_DIA =");
const PREVIA = bloque(src, "const RECAUDO_PREVIA_SEMANAL =", "[", "]") + ";";
const PREVIA_MAP = linea(src, "const RECAUDO_PREVIA_MAP =");
const MESES_ENTRE = bloque(src, "const mesesEntreFechas =", "{", "}") + ";";
const SIMULAR = funcion(src, "function simular(");
// El objeto p por defecto vive en useState({...}) del componente.
const P = bloque(src, "useState({", "{", "}").replace(/^useState\(/, "");

const modulo = [
  MESES,
  MS_DIA,
  PREVIA,
  PREVIA_MAP,
  MESES_ENTRE,
  SIMULAR,
  `const p = ${P};`,
  // CAJA VERAZ (decisión CEO): el motor Python EXCLUYE la provisión NIIF 9 del flujo
  // (va a P&G, no a caja); simular() la incluye en `neto`. Para aislar esa divergencia
  // intencional —ya testeada aparte— se genera la golden con pctProvision=0, de modo
  // que neto/flujo/caja sean comparables al peso. La provisión se valida en
  // test_neto_por_mora_caja_veraz_excluye_provision.
  "p.pctProvision = 0;",
  // paramétrico puro: sin eventos ni overrides (aísla la matemática; IVA fuera).
  "const rows = simular(p, [], {});",
  "globalThis.__RESULT__ = rows;",
].join("\n\n");

// eslint-disable-next-line no-new-func
new Function(modulo)();
const r = globalThis.__RESULT__;

// Proyección de los campos que el motor Python produce (MesProyeccion). Se omiten
// los de balance/P&G del artefacto (cxc, patrimonio, wacc…) que el motor no calcula.
const CAMPOS = [
  "mes", "motos", "cartera", "recaudo", "iniciales", "bruto", "neto",
  "gastosFijos", "gps", "costoNueva", "adelanto", "pagoInv", "fondeo",
  "intDeuda", "egresos", "flujo", "caja", "estado",
];
const golden = {
  meses: r.rows.map((row) => Object.fromEntries(CAMPOS.map((k) => [k, row[k]]))),
  kpis: {
    minCaja: r.minCaja,
    minCajaMes: r.minCajaMes,
    cajaFinal: r.cajaFinal,
    capitalRequerido: r.capitalRequerido,
    mesesCriticos: r.mesesCriticos,
    mesesNegativos: r.mesesNegativos,
  },
};
process.stdout.write(JSON.stringify(golden, null, 1));
