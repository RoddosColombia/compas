import { useState, useMemo, useRef, useEffect } from "react";
import * as XLSX from "xlsx";
import {
  ComposedChart, Area, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer, Legend,
} from "recharts";

// ─── RODDOS brand ───
const C = {
  bg: "#0D0F0E", card: "#161A18", card2: "#1C211E", border: "#262C29",
  green: "#12A312", greenSoft: "#1DC91D", turq: "#0FA9B8", turqSoft: "#76E5EC",
  red: "#E0524D", amber: "#E8A83A", text: "#E8ECE9", dim: "#8B948E",
};
const MESES = ["ENE","FEB","MAR","ABR","MAY","JUN","JUL","AGO","SEP","OCT","NOV","DIC"];

// ─── Recaudo REAL de la cartera preexistente (Modelo Pagos, filas 6-509, 111 créditos) ───
// Serie semanal EXACTA extraída del Modelo Pagos del Excel LoanTape: incluye moras y semanas
// sin pago, por eso es más precisa que un cálculo teórico sf→ef. w = semana (1 = mié 2026-03-04),
// v = recaudo de la semana ($), n = créditos que pagan esa semana.
const RECAUDO_PREVIA_SEMANAL = [
  { w: 1, v: 759600, n: 5 },
  { w: 2, v: 1009500, n: 7 },
  { w: 3, v: 2139500, n: 10 },
  { w: 4, v: 2089400, n: 11 },
  { w: 5, v: 3338100, n: 18 },
  { w: 6, v: 2373100, n: 16 },
  { w: 7, v: 4883100, n: 24 },
  { w: 8, v: 2793100, n: 18 },
  { w: 9, v: 5642100, n: 28 },
  { w: 10, v: 5611700, n: 33 },
  { w: 11, v: 10075800, n: 52 },
  { w: 12, v: 8356800, n: 49 },
  { w: 13, v: 10726800, n: 56 },
  { w: 14, v: 8174800, n: 48 },
  { w: 15, v: 13439300, n: 70 },
  { w: 16, v: 12737500, n: 69 },
  { w: 17, v: 13313800, n: 72 },
  { w: 18, v: 13843200, n: 71 },
  { w: 19, v: 20696100, n: 103 },
  { w: 20, v: 20600100, n: 103 },
  { w: 21, v: 21170900, n: 105 },
  { w: 22, v: 20600100, n: 103 },
  { w: 23, v: 21170900, n: 105 },
  { w: 24, v: 20600100, n: 103 },
  { w: 25, v: 21170900, n: 105 },
  { w: 26, v: 20553600, n: 102 },
  { w: 27, v: 21062400, n: 103 },
  { w: 28, v: 20491600, n: 101 },
  { w: 29, v: 21062400, n: 103 },
  { w: 30, v: 20491600, n: 101 },
  { w: 31, v: 21043500, n: 102 },
  { w: 32, v: 20417800, n: 99 },
  { w: 33, v: 20988600, n: 101 },
  { w: 34, v: 20417800, n: 99 },
  { w: 35, v: 20988600, n: 101 },
  { w: 36, v: 20417800, n: 99 },
  { w: 37, v: 20988600, n: 101 },
  { w: 38, v: 20417800, n: 99 },
  { w: 39, v: 20988600, n: 101 },
  { w: 40, v: 20417800, n: 99 },
  { w: 41, v: 20988600, n: 101 },
  { w: 42, v: 20417800, n: 99 },
  { w: 43, v: 20218600, n: 99 },
  { w: 44, v: 19828900, n: 95 },
  { w: 45, v: 19629700, n: 95 },
  { w: 46, v: 19408900, n: 93 },
  { w: 47, v: 19209700, n: 93 },
  { w: 48, v: 19000900, n: 91 },
  { w: 49, v: 17576700, n: 85 },
  { w: 50, v: 16731900, n: 80 },
  { w: 51, v: 15943700, n: 77 },
  { w: 52, v: 16142900, n: 77 },
  { w: 53, v: 15763800, n: 76 },
  { w: 54, v: 14193700, n: 68 },
  { w: 55, v: 13634500, n: 67 },
  { w: 56, v: 12634400, n: 62 },
  { w: 57, v: 12535000, n: 62 },
  { w: 58, v: 11804700, n: 59 },
  { w: 59, v: 11345300, n: 58 },
  { w: 60, v: 11804700, n: 59 },
  { w: 61, v: 10994300, n: 56 },
  { w: 62, v: 10914000, n: 54 },
  { w: 63, v: 9912800, n: 50 },
  { w: 64, v: 10372200, n: 51 },
  { w: 65, v: 9912800, n: 50 },
  { w: 66, v: 10372200, n: 51 },
  { w: 67, v: 9343100, n: 47 },
  { w: 68, v: 9422500, n: 47 },
  { w: 69, v: 8393600, n: 42 },
  { w: 70, v: 7688300, n: 39 },
  { w: 71, v: 5124900, n: 29 },
  { w: 72, v: 4939400, n: 28 },
  { w: 73, v: 4860000, n: 28 },
  { w: 74, v: 4939400, n: 28 },
  { w: 75, v: 4860000, n: 28 },
  { w: 76, v: 4939400, n: 28 },
  { w: 77, v: 4860000, n: 28 },
  { w: 78, v: 4939400, n: 28 },
  { w: 79, v: 4280300, n: 24 },
  { w: 80, v: 4359700, n: 24 },
  { w: 81, v: 4280300, n: 24 },
  { w: 82, v: 4229700, n: 23 },
  { w: 83, v: 3850500, n: 21 },
  { w: 84, v: 3764900, n: 20 },
  { w: 85, v: 3085500, n: 18 },
  { w: 86, v: 3764900, n: 20 },
  { w: 87, v: 3085500, n: 18 },
  { w: 88, v: 3470000, n: 18 },
  { w: 89, v: 2048800, n: 12 },
  { w: 90, v: 3008200, n: 15 },
  { w: 91, v: 2048800, n: 12 },
  { w: 92, v: 3008200, n: 15 },
  { w: 93, v: 1109400, n: 6 },
  { w: 94, v: 1109400, n: 5 },
  { w: 95, v: 629700, n: 3 },
  { w: 96, v: 629700, n: 3 },
  { w: 97, v: 209900, n: 1 },
];
const RECAUDO_PREVIA_MAP = new Map(RECAUDO_PREVIA_SEMANAL.map((s) => [s.w, s]));

// ─── Serie EXACTA tomada de MODELO_SIMULADOR_2030_CORREGIDO.xlsm (hoja FLUJO DE CAJA) ───
// Incluye financiación real, pagos puntuales (Auteco, DIAN, nómina) y pagos de deuda a
// terceros que el motor paramétrico no puede derivar solo de los supuestos de ventas.
const CAJA_EXCEL_DEFAULT = [
  { mes: "MAY-26", caja: 24000000, flujo: -54798406, ingresoNeto: 56741185, egresos: -111539591, cartera: 56, motos: 20 },
  { mes: "JUN-26", caja: 719452895, flujo: -101047105, ingresoNeto: 119739073, egresos: -220786178, cartera: 103, motos: 48 },
  { mes: "JUL-26", caja: 585100984, flujo: -45094230, ingresoNeto: 169750193, egresos: -214844423, cartera: 150, motos: 1 },
  { mes: "AGO-26", caja: 554714487, flujo: -30386497, ingresoNeto: 188111991, egresos: -218498488, cartera: 210, motos: 51 },
  { mes: "SEP-26", caja: 592465957, flujo: 37751470, ingresoNeto: 262930621, egresos: -225179151, cartera: 260, motos: 52 },
  { mes: "OCT-26", caja: 793080502, flujo: 200614544, ingresoNeto: 258524125, egresos: -57909580, cartera: 312, motos: 53 },
  { mes: "NOV-26", caja: 781797233, flujo: -11283269, ingresoNeto: 295955482, egresos: -307238751, cartera: 366, motos: 54 },
  { mes: "DIC-26", caja: 690541561, flujo: -91255672, ingresoNeto: 398319744, egresos: -489575416, cartera: 415, motos: 55 },
  { mes: "ENE-27", caja: 558037940, flujo: -132503621, ingresoNeto: 365674860, egresos: -498178481, cartera: 467, motos: 56 },
  { mes: "FEB-27", caja: 445635373, flujo: -112402567, ingresoNeto: 394080170, egresos: -506482737, cartera: 510, motos: 57 },
  { mes: "MAR-27", caja: 441696801, flujo: -3938571, ingresoNeto: 510815220, egresos: -514753791, cartera: 552, motos: 58 },
  { mes: "ABR-27", caja: 373433473, flujo: -68263328, ingresoNeto: 455126729, egresos: -523390057, cartera: 605, motos: 59 },
  { mes: "MAY-27", caja: 333447768, flujo: -39985705, ingresoNeto: 492073818, egresos: -532059524, cartera: 659, motos: 60 },
  { mes: "JUN-27", caja: 363797763, flujo: 102703787, ingresoNeto: 643266773, egresos: -540562985, cartera: 708, motos: 61 },
  { mes: "JUL-27", caja: 373188164, flujo: 9390400, ingresoNeto: 555223249, egresos: -545832849, cartera: 759, motos: 62 },
  { mes: "AGO-27", caja: 415908642, flujo: 42720478, ingresoNeto: 597521603, egresos: -554801125, cartera: 822, motos: 63 },
  { mes: "SEP-27", caja: 631477213, flujo: 215568571, ingresoNeto: 779138766, egresos: -563570194, cartera: 879, motos: 64 },
  { mes: "OCT-27", caja: 738853455, flujo: 107376242, ingresoNeto: 679881511, egresos: -572505269, cartera: 941, motos: 65 },
  { mes: "NOV-27", caja: 806526155, flujo: 140026492, ingresoNeto: 721400434, egresos: -581373942, cartera: 1001, motos: 66 },
  { mes: "DIC-27", caja: 1146510085, flujo: 339983930, ingresoNeto: 929728530, egresos: -589744599, cartera: 1046, motos: 67 },
  { mes: "ENE-28", caja: 1328479357, flujo: 181969272, ingresoNeto: 779420509, egresos: -597451237, cartera: 1071, motos: 68 },
  { mes: "FEB-28", caja: 1517784811, flujo: 189305453, ingresoNeto: 794230921, egresos: -604925468, cartera: 1089, motos: 69 },
  { mes: "MAR-28", caja: 1824046213, flujo: 378615194, ingresoNeto: 991014892, egresos: -612399698, cartera: 1107, motos: 70 },
  { mes: "ABR-28", caja: 2025439220, flujo: 201393007, ingresoNeto: 821266936, egresos: -619873929, cartera: 1125, motos: 71 },
  { mes: "MAY-28", caja: 2420836731, flujo: 395397511, ingresoNeto: 1022745671, egresos: -627348160, cartera: 1143, motos: 72 },
  { mes: "JUN-28", caja: 2277915365, flujo: 202318634, ingresoNeto: 837307029, egresos: -634988396, cartera: 1166, motos: 73 },
  { mes: "JUL-28", caja: 2496454952, flujo: 218539587, ingresoNeto: 860836208, egresos: -642296621, cartera: 1179, motos: 74 },
  { mes: "AGO-28", caja: 2917675590, flujo: 421220638, ingresoNeto: 1070991490, egresos: -649770852, cartera: 1197, motos: 75 },
  { mes: "SEP-28", caja: 3139711539, flujo: 222035949, ingresoNeto: 879447036, egresos: -657411088, cartera: 1220, motos: 76 },
  { mes: "OCT-28", caja: 3374726665, flujo: 235015126, ingresoNeto: 899734440, egresos: -664719313, cartera: 1233, motos: 77 },
  { mes: "NOV-28", caja: 3820121536, flujo: 445394870, ingresoNeto: 1117588414, egresos: -672193544, cartera: 1251, motos: 78 },
  { mes: "DIC-28", caja: 4055271042, flujo: 235149507, ingresoNeto: 914950085, egresos: -679800579, cartera: 1273, motos: 79 },
  { mes: "ENE-29", caja: 4517364350, flujo: 462093308, ingresoNeto: 1149235313, egresos: -687142005, cartera: 1287, motos: 80 },
  { mes: "FEB-29", caja: 4764159827, flujo: 246795477, ingresoNeto: 940980100, egresos: -694184623, cartera: 1292, motos: 81 },
  { mes: "MAR-29", caja: 5015533512, flujo: 251373686, ingresoNeto: 953596956, egresos: -702223271, cartera: 1327, motos: 82 },
  { mes: "ABR-29", caja: 5283122817, flujo: 267589305, ingresoNeto: 977154002, egresos: -709564697, cartera: 1341, motos: 83 },
  { mes: "MAY-29", caja: 5780122001, flujo: 496999184, ingresoNeto: 1214038112, egresos: -717038928, cartera: 1359, motos: 84 },
  { mes: "JUN-29", caja: 6049391293, flujo: 269269292, ingresoNeto: 993948456, egresos: -724679164, cartera: 1382, motos: 85 },
  { mes: "JUL-29", caja: 6334881538, flujo: 285490245, ingresoNeto: 1017477634, egresos: -731987389, cartera: 1395, motos: 86 },
  { mes: "AGO-29", caja: 6858598103, flujo: 523716565, ingresoNeto: 1263178185, egresos: -739461620, cartera: 1413, motos: 87 },
  { mes: "SEP-29", caja: 7142708393, flujo: 284110290, ingresoNeto: 1031212146, egresos: -747101856, cartera: 1436, motos: 88 },
  { mes: "OCT-29", caja: 7682648261, flujo: 539939869, ingresoNeto: 1294349950, egresos: -754410081, cartera: 1449, motos: 89 },
  { mes: "NOV-29", caja: 7980521111, flujo: 297872850, ingresoNeto: 1059757162, egresos: -761884312, cartera: 1467, motos: 90 },
  { mes: "DIC-29", caja: 8292248090, flujo: 311726979, ingresoNeto: 1081218326, egresos: -769491347, cartera: 1489, motos: 91 },
  { mes: "ENE-30", caja: 8856711505, flujo: 564463415, ingresoNeto: 1341296188, egresos: -776832773, cartera: 1503, motos: 92 },
  { mes: "FEB-30", caja: 9170892414, flujo: 314180909, ingresoNeto: 1098487913, egresos: -784307004, cartera: 1521, motos: 93 },
  { mes: "MAR-30", caja: 9497977465, flujo: 327085051, ingresoNeto: 1118999090, egresos: -791914039, cartera: 1543, motos: 94 },
  { mes: "ABR-30", caja: 9832601308, flujo: 334623843, ingresoNeto: 1133879308, egresos: -799255466, cartera: 1557, motos: 95 },
  { mes: "MAY-30", caja: 10434639287, flujo: 602037979, ingresoNeto: 1408767676, egresos: -806729696, cartera: 1575, motos: 96 },
  { mes: "JUN-30", caja: 10779988385, flujo: 345349098, ingresoNeto: 1159685829, egresos: -814336731, cartera: 1597, motos: 97 },
  { mes: "JUL-30", caja: 11399143923, flujo: 619155537, ingresoNeto: 1440833695, egresos: -821678158, cartera: 1611, motos: 98 },
  { mes: "AGO-30", caja: 11757230452, flujo: 358086530, ingresoNeto: 1187238918, egresos: -829152388, cartera: 1629, motos: 99 },
  { mes: "SEP-30", caja: 12119273529, flujo: 362043077, ingresoNeto: 1198835701, egresos: -836792624, cartera: 1652, motos: 100 },
  { mes: "OCT-30", caja: 12761821071, flujo: 642547542, ingresoNeto: 1486648392, egresos: -844100850, cartera: 1665, motos: 101 },
  { mes: "NOV-30", caja: 13126155652, flujo: 364334581, ingresoNeto: 1215909661, egresos: -851575080, cartera: 1683, motos: 102 },
  { mes: "DIC-30", caja: 13504285468, flujo: 378129815, ingresoNeto: 1236448704, egresos: -858318889, cartera: 1679, motos: 103 },
];



const fmtM = (v) => {
  if (v === null || v === undefined || isNaN(v)) return "—";
  const m = v / 1e6;
  if (Math.abs(m) >= 1000) return `$${(m/1000).toLocaleString("es-CO",{maximumFractionDigits:2})} mM`;
  return `$${m.toLocaleString("es-CO",{maximumFractionDigits:1})} M`;
};
const fmtPct = (v, d = 1) =>
  v === null || v === undefined || isNaN(v) ? "—" : `${(v*100).toLocaleString("es-CO",{maximumFractionDigits:d})}%`;
const fmtInt = (v) =>
  v === null || v === undefined || v === "" || isNaN(v) ? "" : Math.round(v).toLocaleString("es-CO", { maximumFractionDigits: 0 });

// ─── Calculadora de créditos (deuda con inversionistas) ───
// Tipos: FRANCES (cuota fija), BULLET_MENSUAL (solo intereses/mes, capital al final),
// BULLET_VENC (todo capitaliza y se paga al vencimiento — como las notas convertibles).
const mesesEntreFechas = (isoA, isoB) => {
  const [ay, am] = String(isoA).split("-").map(Number);
  const [by, bm] = String(isoB).split("-").map(Number);
  if (!ay || !am || !by || !bm) return 0;
  return (by - ay) * 12 + (bm - am);
};
const mesKeyDesde = (iso, k) => {
  // mes calendario k meses después de la fecha iso
  const [y0, m0] = String(iso).split("-").map(Number);
  if (!y0 || !m0) return null;
  const t = m0 - 1 + k;
  const y = y0 + Math.floor(t / 12), m = (t % 12 + 12) % 12;
  return { key: `${MESES[m]}-${String(y).slice(2)}`, anio: y, mes: m + 1 };
};
function calcularCredito(inv) {
  const monto = Number(inv.monto) || 0;
  const tasaEA = Number(inv.tasaEA) || 0;
  const i = Math.pow(1 + tasaEA, 1 / 12) - 1;
  const n = Math.max(1, mesesEntreFechas(inv.desembolso, inv.vencimiento));
  const tipo = inv.tipo || "BULLET_MENSUAL";
  const extra = Number(inv.cuotaExtra) || 0;
  let cuotaBase;
  if (tipo === "FRANCES") cuotaBase = i > 0 ? monto * i / (1 - Math.pow(1 + i, -n)) : monto / n;
  else if (tipo === "BULLET_MENSUAL") cuotaBase = monto * i;
  else cuotaBase = 0; // BULLET_VENC: no hay cuota mensual, capitaliza
  const rows = [];
  let saldo = monto, totInteres = 0, totPagado = 0;
  for (let k = 1; k <= n + 240 && saldo > 0.5; k++) {
    const interes = saldo * i;
    let pago;
    if (tipo === "BULLET_VENC") {
      pago = k >= n ? saldo + interes : Math.min(extra, saldo + interes);
    } else if (tipo === "BULLET_MENSUAL") {
      pago = k >= n ? interes + saldo : interes + extra;
    } else {
      pago = cuotaBase + extra;
    }
    if (pago > saldo + interes) pago = saldo + interes;
    const abono = pago - interes;
    saldo = saldo + interes - pago;
    if (tipo === "BULLET_VENC" && pago === 0) { // capitaliza sin pago
      rows.push({ k, ...mesKeyDesde(inv.desembolso, k), interes, abono: 0, pago: 0, saldo });
    } else {
      rows.push({ k, ...mesKeyDesde(inv.desembolso, k), interes, abono, pago, saldo });
    }
    totInteres += interes; totPagado += pago;
    if (saldo <= 0.5) break;
  }
  return { i, n, tipo, cuotaBase, extra, rows, totInteres, totPagado, mesesReales: rows.length,
           pagoAnual: (cuotaBase + extra) * 12 };
}

// ─── Motor de simulación: réplica EXACTA de la macro SimularVentas + hoja FLUJO DE CAJA ───
// Cada moto se coloca en un miércoles real del mes (como hace la macro VBA) y paga
// `plazoSemanas` cuotas semanales desde esa fecha. El pago a Auteco replica la fórmula
// de la fila 29 (saldo rodante del lote facturado, desplazado plazoAutecoDias, neto de
// adelantos) y el fondeo la fila 30. Esa lógica de lotes era lo que faltaba y lo que
// hacía que el simulador diera caja negativa donde el Excel da positiva.
const MS_DIA = 86400000;
function simular(p, eventos = [], overrides = {}) {
  const N = p.horizonteMeses;
  const meses = [], anios = [], mesNums = [];
  for (let i = 0; i < N; i++) {
    const mIdx = (4 + i) % 12, yr = 2026 + Math.floor((4 + i) / 12);
    meses.push(`${MESES[mIdx]}-${String(yr).slice(2)}`);
    anios.push(yr);
    mesNums.push(mIdx + 1);
  }
  const eventosPorMes = {};
  eventos.forEach((ev) => {
    eventosPorMes[ev.mes] = (eventosPorMes[ev.mes] || 0) + (Number(ev.monto) || 0);
  });

  // ── Cohortes por miércoles reales (réplica de SimularMarca en VBA) ──
  // fechaOrigen: semana 1 del Modelo Pagos = miércoles 2026-03-04 (celda N4 del MP).
  // Los sf/ef de CARTERA_REAL_PREVIA usan esta misma numeración.
  const fechaOrigen = Date.UTC(2026, 2, 4); // miércoles 4 de marzo de 2026
  const semanaDeFecha = (t) => Math.floor((t - fechaOrigen) / (7 * MS_DIA)) + 1;

  const miercolesDelMes = (yr, mo1) => {
    // primer miércoles >= día 1 del mes, luego cada 7 días mientras siga en el mes
    let t = Date.UTC(yr, mo1 - 1, 1);
    while (new Date(t).getUTCDay() !== 3) t += MS_DIA;
    const arr = [];
    while (new Date(t).getUTCMonth() === mo1 - 1) { arr.push(t); t += 7 * MS_DIA; }
    return arr;
  };

  const rampa = p.rampaMotos || [];
  // rampa: número (usa % Apache global) u objeto { total, apache, enCartera, iniciales }
  // enCartera: true = las motos ya están en CARTERA_REAL_PREVIA (no crear cohortes nuevas,
  // pero sí cuentan para lote/adelanto/costos/iniciales). iniciales: monto real override.
  const motosMesArr = [], apacheMesArr = [], enCarteraArr = [], inicialesOverride = [];
  // Crecimiento como la columna C del SIMULADOR: encadenado con redondeo mes a mes
  // C10 = ROUND(C9 × (1 + N5)) — con 1% mensual da 50, 51, 52, 53… (+1/mes), distinto
  // de ROUND(50 × 1.01^k). Replicamos el encadenamiento exacto.
  let motosEncadenadas = p.motosMes;
  for (let m = 0; m < N; m++) {
    let total, apache, enCartera = false, iniOv = null;
    if (m < rampa.length) {
      const it = rampa[m];
      if (typeof it === "object" && it !== null) {
        total = it.total; apache = it.apache ?? Math.round(it.total * p.pctApache);
        enCartera = !!it.enCartera; iniOv = it.iniciales ?? null;
      } else { total = it; apache = Math.round(it * p.pctApache); }
    } else {
      if (m === rampa.length) motosEncadenadas = p.motosMes;
      else motosEncadenadas = Math.floor(motosEncadenadas * (1 + p.crecMensual / 100) + 0.5);
      total = motosEncadenadas;
      apache = Math.round(total * p.pctApache);
    }
    motosMesArr.push(total);
    apacheMesArr.push(apache);
    enCarteraArr.push(enCartera);
    inicialesOverride.push(iniOv);
  }

  // altas[semana] = { r: motos Raider, a: motos Apache } colocadas esa semana
  const maxSem = semanaDeFecha(Date.UTC(2026 + Math.ceil((4 + N) / 12), 11, 31)) + p.plazoSemanas + 4;
  const altasR = new Array(maxSem + 2).fill(0);
  const altasA = new Array(maxSem + 2).fill(0);
  // nw de la hoja SIMULADOR (col "SEMANAS EN MES"), desde JUL-26: 5,4,5, luego 4,4,5 repetido.
  // La macro usa este nw para repartir las motos del mes, no el conteo real de miércoles.
  const nwSimulador = (m) => {
    const i = m - 2; // índice desde JUL-26 (m=0 es MAY-26)
    if (i < 0) return null;
    if (i === 0) return 5;
    if (i === 1) return 4;
    if (i === 2) return 5;
    return (i - 3) % 3 === 2 ? 5 : 4;
  };
  for (let m = 0; m < N; m++) {
    if (enCarteraArr[m]) continue; // estas motos ya pagan dentro de CARTERA_REAL_PREVIA
    const motos = motosMesArr[m];
    if (motos <= 0) continue;
    // split como la macro: apache = ROUND(total*pct), raider = total - apache (con mix de rampa si aplica)
    const nmApache = apacheMesArr[m];
    const nmRaider = motos - nmApache;
    const wednesdays = miercolesDelMes(anios[m], mesNums[m]);
    const nw = nwSimulador(m) ?? wednesdays.length;
    const firstWed = wednesdays[0];
    // distribución de la macro: mpw = max(1, round(nm/nw)) por semana; el resto en la última
    const distribuir = (nm, arr) => {
      if (nm <= 0) return;
      const mpw = Math.max(1, Math.round(nm / nw));
      let pd = nm;
      for (let iw = 0; iw < nw && pd > 0; iw++) {
        const mw = iw === nw - 1 ? pd : Math.min(mpw, pd);
        const sem = semanaDeFecha(firstWed + iw * 7 * MS_DIA);
        if (sem >= 1 && sem < arr.length) arr[sem] += mw;
        pd -= mw;
      }
    };
    distribuir(nmRaider, altasR);
    distribuir(nmApache, altasA);
  }
  const cumR = [0], cumA = [0];
  for (let w = 0; w < altasR.length; w++) {
    cumR.push(cumR[w] + altasR[w]);
    cumA.push(cumA[w] + altasA[w]);
  }
  // activos pagando en la semana w: colocados en (w - plazo, w]
  const actR = (w) => cumR[Math.min(w + 1, cumR.length - 1)] - cumR[Math.max(0, Math.min(w + 1 - p.plazoSemanas, cumR.length - 1))];
  const actA = (w) => cumA[Math.min(w + 1, cumA.length - 1)] - cumA[Math.max(0, Math.min(w + 1 - p.plazoSemanas, cumA.length - 1))];
  // cartera REAL previa: serie EXACTA por semana del Modelo Pagos (incluye moras y semanas sin pago)
  const recaudoPrevio = (w) => RECAUDO_PREVIA_MAP.get(w)?.v || 0;
  const activosPrevios = (w) => RECAUDO_PREVIA_MAP.get(w)?.n || 0;
  const saldoPrevio = (w) => {
    let s = 0;
    for (const it of RECAUDO_PREVIA_SEMANAL) if (it.w > w) s += it.v;
    return s;
  };
  const saldoCartera = (w) => {
    let os = 0;
    for (let k = 0; k < p.plazoSemanas; k++) {
      const s = w - k;
      if (s < 0) break;
      const rem = p.plazoSemanas - k - 1;
      os += (altasR[s] || 0) * rem * p.cuotaRaider + (altasA[s] || 0) * rem * p.cuotaApache;
    }
    return os;
  };
  // semanas (miércoles) que caen dentro de cada mes del horizonte
  const semanasDelMes = [];
  for (let m = 0; m < N; m++) {
    semanasDelMes.push(miercolesDelMes(anios[m], mesNums[m]).map(semanaDeFecha));
  }

  // ── Valor facturado Auteco por mes (INVENTARIO fila 16) y flujo de pago (FC filas 28-30) ──
  // Modelo LoanTape: el lote se factura con split FRACCIONARIO en valor (motos × %mix × costo),
  // no por unidades enteras — INVENTARIO f14/f15 = motos × 0.7 × costoR + motos × 0.3 × costoA.
  const loteMes = motosMesArr.map((motos, m) => {
    if (m < rampa.length) {
      // meses de rampa real: lote exacto de Facturación si viene en la rampa, o unidades exactas
      const it = rampa[m];
      if (typeof it === "object" && it !== null && it.lote != null) return it.lote;
      const nmApache = apacheMesArr[m];
      return (motos - nmApache) * p.costoRaider + nmApache * p.costoApache;
    }
    return motos * (1 - p.pctApache) * p.costoRaider + motos * p.pctApache * p.costoApache;
  });
  // fila 28 (adelanto Auteco): MAY-26 = 0; meses con dato real de Facturación usan el adelanto
  // REAL (override en la rampa, ej. JUN-26 = -80,81M); los proyectados usan -motos × adelanto/moto
  const adelantoMes = motosMesArr.map((motos, m) => {
    if (m === 0) return 0;
    if (m < rampa.length && typeof rampa[m] === "object" && rampa[m] !== null && rampa[m].adelanto != null)
      return rampa[m].adelanto;
    return -motos * p.adelantoAuteco;
  });
  const delayPago = Math.floor(p.plazoAutecoDias / 30);   // INT(C43/30): meses de espera para pagar el lote
  const delayBase = Math.floor(p.baseAutecoDias / 30);    // INT(C45/30): meses sin costo de fondeo
  const mesesInteres = Math.max(0, delayPago - delayBase);

  // fila 29 (pago inventario, saldo rodante): pago[m] = max(pago[m-1],0) − lote[m−delay] − adelanto[m]
  // Si hay override editado para el mes, se usa ese valor y la recurrencia lo propaga (como
  // sobrescribir la celda en el Excel: los meses siguientes parten de MAX(valor editado, 0)).
  const pagoInvMes = new Array(N).fill(0);
  for (let m = 0; m < N; m++) {
    const ov = overrides[meses[m]];
    if (ov && ov.pagoInv != null) { pagoInvMes[m] = ov.pagoInv; continue; }
    if (m < delayPago) { pagoInvMes[m] = 0; continue; }
    if (m === delayPago) {
      let sumAde = 0;
      for (let k = 0; k <= delayPago && k < N; k++) sumAde += adelantoMes[k];
      pagoInvMes[m] = -(loteMes[0] || 0) - sumAde;
    } else {
      const lote = loteMes[m - delayPago] || 0;
      pagoInvMes[m] = Math.max(pagoInvMes[m - 1], 0) - lote - adelantoMes[m];
    }
  }
  // fila 30 (fondeo): −lote[m−delay] × tasa × mesesInteres desde que empieza a pagarse
  const fondeoMes = new Array(N).fill(0);
  for (let m = 0; m < N; m++) {
    if (m < delayPago) {
      if (m === delayBase + 1) {
        const lote = loteMes[m - delayBase] || 0;
        const ade = adelantoMes[m - delayBase] || 0;
        fondeoMes[m] = -(lote + ade) * p.tasaAuteco;
      }
    } else {
      fondeoMes[m] = -(loteMes[m - delayPago] || 0) * p.tasaAuteco * mesesInteres;
    }
  }

  const rows = [];
  let caja = p.cajaInicial, minCaja = Infinity, minCajaMes = "";
  let totRecaudo = 0, totFondeo = 0, carteraPico = 0;
  let mesesCriticos = 0, mesesNegativos = 0;
  let utilidadAcum = 0;

  for (let m = 0; m < N; m++) {
    // recaudo: cada miércoles del mes, todos los créditos activos pagan su cuota (FC fila 13)
    // = motos nuevas simuladas + cartera REAL previa (créditos preexistentes en Modelo Pagos)
    let recaudo = 0;
    for (const w of semanasDelMes[m])
      recaudo += actR(w) * p.cuotaRaider + actA(w) * p.cuotaApache + recaudoPrevio(w);

    const motos = motosMesArr[m];
    const nmApache = apacheMesArr[m];
    const nmRaider = motos - nmApache;
    // FC fila 14 (LoanTape): iniciales con split fraccionario para meses simulados,
    // unidades exactas para la rampa real, y override cuando hay valor real de Facturación
    const iniciales = inicialesOverride[m] ?? (m < rampa.length
      ? nmRaider * p.iniRaider + nmApache * p.iniApache
      : motos * (1 - p.pctApache) * p.iniRaider + motos * p.pctApache * p.iniApache);
    const bruto = recaudo + iniciales;

    // ajustes por mora (FC filas 17-20)
    const mora = -bruto * p.pctMora;
    const recu = -mora * p.pctRecuperacion;
    const def = -bruto * p.pctDefault;
    const prov = -bruto * p.pctProvision;
    const neto = bruto + mora + recu + def + prov;

    // cartera activa al cierre del mes = simulados + cartera real previa (INVENTARIO fila 13)
    const wRef = semanasDelMes[m][semanasDelMes[m].length - 1] ?? 0;
    const cartera = actR(wRef) + actA(wRef) + activosPrevios(wRef);

    const ovMes = overrides[meses[m]] || {};
    const gastosFijos = ovMes.gastosFijos != null ? ovMes.gastosFijos : -p.gastosFijos; // FC fila 24 (editable)
    const gps = -cartera * p.gpsMoto;                                   // FC fila 25
    // FC fila 26: los intereses arrancan en JUL-26 (columnas D y E = 0) y corren todo el horizonte
    const mesIniDeuda = p.mesInicioDeuda ?? 0;
    const intDeuda = m >= mesIniDeuda && m < p.mesesDeuda ? -p.deuda * p.tasaDeuda : 0;
    const costoNueva = -motos * p.costoMotoNueva;                       // FC fila 27
    const adelanto = adelantoMes[m];                                    // FC fila 28
    const fondeo = fondeoMes[m];                                        // FC fila 30

    // FC fila 31: TOTAL EGRESOS suma la fila 29 tal cual (positiva o negativa),
    // igual que el Excel — un saldo positivo reduce egresos ese mes
    const egresos = gastosFijos + gps + intDeuda + costoNueva + adelanto + pagoInvMes[m] + fondeo;
    const flujo = neto + egresos;                                       // FC fila 34
    let inyeccion = 0;
    if (m === p.mesInyeccion && p.inyeccion > 0) inyeccion = p.inyeccion;
    const extra = eventosPorMes[meses[m]] || 0;
    // FC fila 35: la caja del PRIMER mes es fija (D35 = PARAMETROS!C61); el flujo de ese
    // mes no la mueve. Desde el segundo mes, caja = caja anterior + flujo + eventos.
    if (m === 0 && (p.cajaInicialFija ?? true)) caja = p.cajaInicial + extra + inyeccion;
    else caja += flujo + inyeccion + extra;

    // P&G devengado: costo del lote reconocido en el mes de venta
    const loteBrutoMes = loteMes[m];
    const utilidadMes = neto + gastosFijos + gps + costoNueva + intDeuda + fondeo - loteBrutoMes;
    utilidadAcum += utilidadMes;

    const margenBruto = bruto - loteBrutoMes;
    const margenBrutoPct = bruto > 0 ? margenBruto / bruto : null;
    const margenNetoPct = neto > 0 ? utilidadMes / neto : null;

    // balance aproximado (incluye saldo por cobrar de la cartera real previa)
    const cxc = saldoCartera(wRef) + saldoPrevio(wRef);
    let cxpAuteco = 0;
    for (let k = Math.max(0, m - delayPago + 1); k <= m; k++)
      cxpAuteco += (loteMes[k] || 0) + (adelantoMes[k] || 0);
    const activos = Math.max(0, caja) + cxc;
    const pasivos = p.deuda + cxpAuteco;
    const patrimonio = activos - pasivos;

    const estado = caja < 0 ? "NEGATIVO" : caja < p.cajaMinima ? "CRÍTICO" : "OK";
    if (estado === "NEGATIVO") mesesNegativos++;
    else if (estado === "CRÍTICO") mesesCriticos++;
    if (caja < minCaja) { minCaja = caja; minCajaMes = meses[m]; }
    totRecaudo += recaudo; totFondeo += fondeo;
    if (cartera > carteraPico) carteraPico = cartera;

    rows.push({
      mes: meses[m], anio: anios[m], motos, cartera: Math.round(cartera),
      recaudo, iniciales, bruto, neto,
      gastosFijos, gps, costoNueva, adelanto, pagoInv: pagoInvMes[m], fondeo, intDeuda,
      egresos, flujo, flujoTotal: flujo + inyeccion + extra, inyeccion, extra, caja, estado, loteBruto: loteBrutoMes,
      utilidad: utilidadMes, cxc, cxpAuteco, activos, pasivos, patrimonio,
      margenBruto, margenBrutoPct, margenNetoPct,
    });
  }

  // ── Indicadores por año ──
  const porAnio = [];
  const years = [...new Set(anios)];
  for (const y of years) {
    const rws = rows.filter((r) => r.anio === y);
    const n = rws.length;
    const uti = rws.reduce((s, r) => s + r.utilidad, 0);
    const utiAnualizada = uti * (12 / n);
    const ingr = rws.reduce((s, r) => s + r.neto, 0);
    const actProm = rws.reduce((s, r) => s + r.activos, 0) / n;
    const patProm = rws.reduce((s, r) => s + r.patrimonio, 0) / n;
    const cxpProm = rws.reduce((s, r) => s + r.cxpAuteco, 0) / n;
    const fondeoY = -rws.reduce((s, r) => s + r.fondeo, 0);
    const intY = -rws.reduce((s, r) => s + r.intDeuda, 0);
    porAnio.push({
      anio: y, n, utilidad: uti, utiAnualizada, ingresos: ingr,
      actProm, patProm, cxpProm, fondeoY, intY,
      roe: patProm > 0 ? utiAnualizada / patProm : null,
      roa: actProm > 0 ? utiAnualizada / actProm : null,
      margen: ingr > 0 ? uti / ingr : null,
    });
  }

  // ── WACD y WACC (promedios del horizonte) ──
  const nT = rows.length;
  const cxpPromT = rows.reduce((s, r) => s + r.cxpAuteco, 0) / nT;
  const patPromT = rows.reduce((s, r) => s + r.patrimonio, 0) / nT;
  const fondeoAnual = (-totFondeo) * (12 / nT);
  const kdAuteco = cxpPromT > 0 ? fondeoAnual / cxpPromT : 0;               // costo efectivo EA
  const kdInversores = Math.pow(1 + p.tasaDeuda, 12) - 1;                    // EA desde %/mes
  const D = cxpPromT + p.deuda;
  const wacd = D > 0 ? (cxpPromT * kdAuteco + p.deuda * kdInversores) / D : 0;
  const E = Math.max(0, patPromT);
  const V = D + E;
  const wacc = V > 0 ? (E / V) * p.ke + (D / V) * wacd * (1 - p.tasaImpuestos) : null;

  const capitalRequerido = Math.max(0, p.cajaMinima - minCaja);
  return {
    rows, porAnio, minCaja, minCajaMes, totRecaudo, totFondeo,
    carteraPico: Math.round(carteraPico), mesesCriticos, mesesNegativos,
    cajaFinal: caja, capitalRequerido, utilidadAcum,
    wacd, wacc, kdAuteco, kdInversores, D, E,
  };
}

// ─── UI helpers ───
function Num({ label, value, onChange, step = 1, suffix, min, max, hint }) {
  return (
    <label style={{ display: "block", marginBottom: 10 }}>
      <div style={{ fontSize: 11, color: C.dim, marginBottom: 3, letterSpacing: ".04em" }}>
        {label}{hint && <span style={{ color: C.turq }}> · {hint}</span>}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <input
          type="number" value={value} step={step} min={min} max={max}
          onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
          style={{
            width: "100%", background: C.card2, border: `1px solid ${C.border}`,
            borderRadius: 6, color: C.text, padding: "6px 8px", fontSize: 13,
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          }}
        />
        {suffix && <span style={{ fontSize: 11, color: C.dim, whiteSpace: "nowrap" }}>{suffix}</span>}
      </div>
    </label>
  );
}

function Seccion({ titulo, abierta, onToggle, children }) {
  return (
    <div style={{ borderBottom: `1px solid ${C.border}` }}>
      <button onClick={onToggle} style={{
        width: "100%", background: "none", border: "none", color: C.text,
        padding: "11px 2px", display: "flex", justifyContent: "space-between",
        alignItems: "center", cursor: "pointer", fontSize: 12.5, fontWeight: 600,
        letterSpacing: ".06em", textTransform: "uppercase",
      }}>
        <span>{titulo}</span>
        <span style={{ color: C.turq, fontSize: 11 }}>{abierta ? "−" : "+"}</span>
      </button>
      {abierta && <div style={{ paddingBottom: 12 }}>{children}</div>}
    </div>
  );
}

function KPI({ label, value, sub, tone }) {
  const col = tone === "bad" ? C.red : tone === "warn" ? C.amber : tone === "good" ? C.greenSoft : C.turqSoft;
  return (
    <div style={{
      background: C.card, border: `1px solid ${C.border}`, borderRadius: 10,
      padding: "12px 14px", flex: "1 1 150px", minWidth: 145,
    }}>
      <div style={{ fontSize: 10.5, color: C.dim, letterSpacing: ".07em", textTransform: "uppercase" }}>{label}</div>
      <div style={{
        fontSize: 20, fontWeight: 700, color: col, marginTop: 3,
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
      }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: C.dim, marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

// Input de monto en pesos: muestra separador de miles (796.500.000) y edita como texto plano al enfocar
function MontoInput({ value, onChange, width = 120, style, allowEmpty = false, placeholder = "—" }) {
  const [focused, setFocused] = useState(false);
  const [text, setText] = useState(String(value ?? ""));
  useEffect(() => { if (!focused) setText(value == null ? "" : String(value)); }, [value, focused]);
  return (
    <input
      type="text" inputMode="numeric" placeholder={placeholder}
      value={focused ? text : (value == null ? "" : fmtInt(value))}
      onFocus={(e) => { setFocused(true); setText(value == null ? "" : String(value)); e.target.select(); }}
      onBlur={() => setFocused(false)}
      onChange={(e) => {
        const raw = e.target.value.replace(/[^\d-]/g, "");
        setText(raw);
        if (raw === "" && allowEmpty) { onChange(null); return; }
        const n = raw === "" || raw === "-" ? 0 : parseInt(raw, 10) || 0;
        onChange(n);
      }}
      style={{
        width, background: C.card2, border: `1px solid ${C.border}`, borderRadius: 5,
        color: value == null ? C.dim : value >= 0 ? C.text : C.red, padding: "3px 6px", fontSize: 11.5, textAlign: "right",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        ...style,
      }}
    />
  );
}

export default function RoddosSimulador() {
  const [p, setP] = useState({
    horizonteMeses: 176, // MAY-26 → DIC-40
    motosMes: 50, crecMensual: 1, pctApache: 0.30, plazoSemanas: 78,
    rampaMotos: [
      { total: 20, apache: 0, enCartera: true, iniciales: 26110000, lote: 109816454 },  // MAY-26: 20 motos reales (18 Raider + 2 Sport), ya en cartera previa
      { total: 48, apache: 17, enCartera: true, iniciales: 80810000, adelanto: -80810000 }, // JUN-26: 48 reales (fact. 174,8M + 115,9M), iniciales y adelanto reales de Facturación
    ],
    // ✔ parámetros verificados contra MODELO_SIMULADOR_2030_CORREGIDO.xlsm (PARAMETROS)
    cuotaRaider: 164900, cuotaApache: 209900,
    iniRaider: 1070000, iniApache: 1401000,
    costoRaider: 5638974, costoApache: 6818517,
    plazoAutecoDias: 150, baseAutecoDias: 90, tasaAuteco: 0.016, adelantoAuteco: 970000,
    pctMora: 0.03, pctRecuperacion: 0.40, pctDefault: 0.03, pctProvision: 0.02,
    gastosFijos: 125206342.23178737, gpsMoto: 33201, costoMotoNueva: 692005,
    deuda: 28527080, tasaDeuda: 0.115679557809632, mesesDeuda: 14, mesInicioDeuda: 2, // intereses solo JUL-26→JUN-27 (FC fila 26)
    cajaInicial: 24000000, cajaMinima: 125000000,
    cajaInicialFija: true,
    inyeccion: 0, mesInyeccion: 0,
    ke: 0.25, tasaImpuestos: 0.35,
  });
  const set = (k) => (v) => setP((s) => ({ ...s, [k]: v }));
  const [sec, setSec] = useState({ ventas: true, producto: false, auteco: true, mora: false, opex: false, capital: true, indicadores: true });
  const tg = (k) => () => setSec((s) => ({ ...s, [k]: !s[k] }));
  const [verTabla, setVerTabla] = useState(false);

  // ── Datos reales: ingresos, presupuesto y deuda con inversionistas ──
  // Ejemplos editables para los primeros meses — reemplázalos por tus cifras reales.
  const [ingresosReales, setIngresosReales] = useState(() => {
    const arr = new Array(p.horizonteMeses).fill(null);
    [82000000, 95000000, 108000000, 121000000, 133000000, 145000000].forEach((v, i) => { arr[i] = v; });
    return arr;
  });
  const [gastosReales, setGastosReales] = useState(() => {
    const arr = new Array(p.horizonteMeses).fill(null);
    [118500000, 122300000, 126900000, 129800000, 131200000, 135600000].forEach((v, i) => { arr[i] = v; });
    return arr;
  });
  const [verIngresos, setVerIngresos] = useState(true);
  const [verGastos, setVerGastos] = useState(false);

  // ── Deudas reales de RODDOS (cargadas de Deudas_Roddos.xlsx) ──
  // afectaCaja viene desmarcado en las que YA están reflejadas en el flujo base del Excel
  // (Diana, Cesar 1 y 2, Andrés vía eventos; Fabian/FEC vía el parámetro "Deuda inversores").
  // Raul y David NO están en el FLUJO DE CAJA del Excel — márcalas si quieres el flujo completo.
  const [inversionistas, setInversionistas] = useState([
    { id: 1, nombre: "Raul", monto: 130000000, tasaEA: 0.4758627, tipo: "FRANCES", cuotaExtra: 0,
      desembolso: "2024-01-01", vencimiento: "2029-01-01", estado: "Activo", afectaCaja: false },
    { id: 2, nombre: "Andres Cano", monto: 295000000, tasaEA: 0.15, tipo: "BULLET_MENSUAL", cuotaExtra: 0,
      desembolso: "2025-07-01", vencimiento: "2028-06-01", estado: "Activo", afectaCaja: false },
    { id: 3, nombre: "David Martinez", monto: 170000000, tasaEA: 0.18, tipo: "BULLET_MENSUAL", cuotaExtra: 0,
      desembolso: "2025-09-01", vencimiento: "2030-09-01", estado: "Activo", afectaCaja: false },
    { id: 4, nombre: "Cesar Robles 1", monto: 51500000, tasaEA: 0.12, tipo: "BULLET_VENC", cuotaExtra: 0,
      desembolso: "2024-11-25", vencimiento: "2027-11-25", estado: "Activo", afectaCaja: false },
    { id: 5, nombre: "Cesar Robles 2", monto: 51500000, tasaEA: 0.12, tipo: "BULLET_VENC", cuotaExtra: 0,
      desembolso: "2025-03-02", vencimiento: "2028-03-02", estado: "Activo", afectaCaja: false },
    { id: 6, nombre: "Diana Sanabria", monto: 51500000, tasaEA: 0.12, tipo: "BULLET_VENC", cuotaExtra: 0,
      desembolso: "2024-06-12", vencimiento: "2027-06-12", estado: "Activo", afectaCaja: false },
    { id: 7, nombre: "Fabian (FEC)", monto: 28527080, tasaEA: 0.8895116, tipo: "FRANCES", cuotaExtra: 0,
      desembolso: "2026-06-15", vencimiento: "2027-06-15", estado: "Activo", afectaCaja: false },
    { id: 8, nombre: "Miguel (propuesta)", monto: 400000000, tasaEA: 0.20, tipo: "BULLET_MENSUAL", cuotaExtra: 0,
      desembolso: "2026-08-01", vencimiento: "2029-08-01", estado: "Activo", afectaCaja: false },
    { id: 9, nombre: "Esposa Miguel (propuesta)", monto: 140000000, tasaEA: 0.16, tipo: "BULLET_MENSUAL", cuotaExtra: 0,
      desembolso: "2026-08-01", vencimiento: "2029-08-01", estado: "Activo", afectaCaja: false },
  ]);
  const nextInvId = useRef(10);
  const addInversionista = () => {
    setInversionistas((s) => [...s, {
      id: nextInvId.current++, nombre: "Nuevo inversionista", monto: 0, tasaEA: 0.18,
      tipo: "BULLET_MENSUAL", cuotaExtra: 0,
      desembolso: "2026-07-01", vencimiento: "2027-07-01", estado: "Activo", afectaCaja: true,
    }]);
  };
  const [detalleInvId, setDetalleInvId] = useState(null);

  // ── Hoja GASTOS del Excel: rubros de gastos fijos vinculados al parámetro del modelo ──
  const [gastosDetalle, setGastosDetalle] = useState([
    { id: 1, cat: "PERSONAL", desc: "Salario Alexa", monto: 4500000 },
    { id: 2, cat: "PERSONAL", desc: "Salario Liz", monto: 2200000 },
    { id: 3, cat: "PERSONAL", desc: "Parafiscales Alexa", monto: 1328400 },
    { id: 4, cat: "PERSONAL", desc: "Parafiscales Liz", monto: 649440 },
    { id: 5, cat: "PERSONAL", desc: "Liquidacion Liliana", monto: 533400 },
    { id: 6, cat: "PERSONAL", desc: "Santiago Echeverry (Coord. logístico y operativo)", monto: 4818860.723135 },
    { id: 7, cat: "OPERACIONES", desc: "Arrend. local Cll 127", monto: 3614953 },
    { id: 8, cat: "OPERACIONES", desc: "Arrend. oficina", monto: 3614953 },
    { id: 9, cat: "OPERACIONES", desc: "Agua y luz oficina", monto: 250000 },
    { id: 10, cat: "OPERACIONES", desc: "Agua y luz local", monto: 250000 },
    { id: 11, cat: "OPERACIONES", desc: "ETB Internet", monto: 180000 },
    { id: 12, cat: "OPERACIONES", desc: "Claro Telefonia", monto: 220000 },
    { id: 13, cat: "OPERACIONES", desc: "Aseo oficina", monto: 400000 },
    { id: 14, cat: "OPERACIONES", desc: "Cafeteria", monto: 650000 },
    { id: 15, cat: "OPERACIONES", desc: "Transporte / Peajes", monto: 350000 },
    { id: 16, cat: "OPERACIONES", desc: "Papeleria", monto: 80000 },
    { id: 17, cat: "OPERACIONES", desc: "Freelance", monto: 1000000 },
    { id: 18, cat: "OPERACIONES", desc: "Contador tercerizacion", monto: 1500000 },
    { id: 19, cat: "OPERACIONES", desc: "Contingencia", monto: 37000000 },
    { id: 20, cat: "FINANCIERO", desc: "Intereses David Martinez", monto: 2361033 },
    { id: 21, cat: "FINANCIERO", desc: "Intereses Andres Cano", monto: 2240000 },
    { id: 22, cat: "FINANCIERO", desc: "Intereses Raul Vasquez", monto: 5000000 },
    { id: 23, cat: "FINANCIERO", desc: "Comisiones Nequi", monto: 80000 },
    { id: 24, cat: "FINANCIERO", desc: "Comisiones Bancolombia", monto: 50000 },
    { id: 25, cat: "FINANCIERO", desc: "Gravamen 4x1000", monto: 114000 },
    { id: 26, cat: "FINANCIERO", desc: "Fee Finca garantía Auteco", monto: 14000000 },
    { id: 27, cat: "FINANCIERO", desc: "Deuda Luis Miguel", monto: 6123788.19989248 },
    { id: 28, cat: "FINANCIERO", desc: "Deuda Esposa Luis Miguel", monto: 1742319.30875989 },
    { id: 29, cat: "CXC SOCIOS", desc: "Retiro Andres Sanjuan (COO)", monto: 7546765 },
    { id: 30, cat: "CXC SOCIOS", desc: "Retiro Ivan Echeverri (CMO)", monto: 7546765 },
    { id: 31, cat: "CXC SOCIOS", desc: "Retiro Fabian (CFO)", monto: 7546765 },
    { id: 32, cat: "MARKETING", desc: "Publicidad Meta/Google", monto: 2000000 },
    { id: 33, cat: "MARKETING", desc: "Eventos / Referidos", monto: 200000 },
    { id: 34, cat: "TECNOLOGIA", desc: "Sofia Operadora", monto: 1300000 },
    { id: 35, cat: "TECNOLOGIA", desc: "Anthropic API (SISMO)", monto: 60000 },
    { id: 36, cat: "TECNOLOGIA", desc: "Claude.ai Pro", monto: 850000 },
    { id: 37, cat: "TECNOLOGIA", desc: "Mercately WhatsApp", monto: 430000 },
    { id: 38, cat: "TECNOLOGIA", desc: "Alegra ERP", monto: 219900 },
    { id: 39, cat: "TECNOLOGIA", desc: "Render hosting", monto: 30000 },
    { id: 40, cat: "TECNOLOGIA", desc: "MongoDB Atlas", monto: 25000 },
    { id: 41, cat: "COSTOS PLATAFORMA", desc: "Risk Seal - Gestion riesgo", monto: 1650000 },
    { id: 42, cat: "COSTOS PLATAFORMA", desc: "Palenca - Plataforma operativa", monto: 950000 },
  ]);
  const nextGastoId = useRef(43);
  const [verHojaGastos, setVerHojaGastos] = useState(false);
  const addGasto = () => setGastosDetalle((s) => [...s, { id: nextGastoId.current++, cat: "OPERACIONES", desc: "Nuevo rubro", monto: 0 }]);
  const updateGasto = (id, campo, valor) => setGastosDetalle((s) => s.map((g) => (g.id === id ? { ...g, [campo]: valor } : g)));
  const removeGasto = (id) => setGastosDetalle((s) => s.filter((g) => g.id !== id));
  const totalGastosDetalle = gastosDetalle.reduce((s, g) => s + (Number(g.monto) || 0), 0);
  // vínculo automático: cualquier cambio en la hoja de gastos actualiza el parámetro "Gastos fijos / mes"
  useEffect(() => {
    setP((s) => (Math.abs(s.gastosFijos - totalGastosDetalle) > 0.5 ? { ...s, gastosFijos: totalGastosDetalle } : s));
  }, [totalGastosDetalle]);
  const updateInversionista = (id, campo, valor) => {
    setInversionistas((s) => s.map((inv) => (inv.id === id ? { ...inv, [campo]: valor } : inv)));
  };
  const removeInversionista = (id) => setInversionistas((s) => s.filter((inv) => inv.id !== id));

  // ── Flujos automáticos de deuda con inversionistas (como en el Excel: entra el
  // desembolso, se pagan intereses cada mes y el capital al vencimiento) ──
  const fechaAMesKey = (iso) => {
    const [y, mo] = String(iso).split("-").map(Number);
    if (!y || !mo) return null;
    return `${MESES[mo - 1]}-${String(y).slice(2)}`;
  };
  const eventosDeuda = useMemo(() => {
    const evs = [];
    for (const inv of inversionistas) {
      if (!inv.afectaCaja || !(Number(inv.monto) > 0)) continue;
      const calc = calcularCredito(inv);
      // desembolso: entra el capital (solo si cae dentro del horizonte, desde MAY-26)
      const desemKey = fechaAMesKey(inv.desembolso);
      const [dy] = String(inv.desembolso).split("-").map(Number);
      if (dy >= 2026) evs.push({ mes: desemKey, monto: Number(inv.monto), desc: `Desembolso ${inv.nombre}` });
      // pagos según el cronograma real del crédito (cuota calculada + adicional)
      for (const row of calc.rows) {
        if (row.pago > 0) evs.push({ mes: row.key, monto: -row.pago, desc: `Pago ${inv.nombre}` });
      }
    }
    return evs;
  }, [inversionistas]);

  // ── Eventos extraordinarios de caja (hallados en MODELO_SIMULADOR_2030_CORREGIDO.xlsm) ──
  // Estos son movimientos reales de caja que el motor paramétrico no puede derivar de los
  // supuestos de ventas: financiación, pagos puntuales e impuestos, y pagos de deuda a terceros.
  const [eventosExtra, setEventosExtra] = useState([
    { id: 2, mes: "JUN-26", monto: 796500000, desc: "Financiero (crédito/aporte)" },
    { id: 3, mes: "JUN-26", monto: 21866108, desc: "Ajuste gastos JUN (GASTOS I36)" },
    { id: 4, mes: "JUL-26", monto: -52000000, desc: "Faltante Auteco" },
    { id: 5, mes: "JUL-26", monto: -25000000, desc: "Plantillas (JUL)" },
    { id: 6, mes: "JUL-26", monto: -14000000, desc: "DIAN" },
    { id: 7, mes: "JUL-26", monto: 3484639, desc: "Ajuste recurrente JUL (gastos + caja, ×2 como el Excel)" },
    { id: 8, mes: "AGO-26", monto: -6250000, desc: "Plantillas (AGO)" },
    { id: 9, mes: "AGO-26", monto: 1742319, desc: "Ajuste recurrente (gastos)" },
    { id: 10, mes: "SEP-26", monto: 1742319, desc: "Ajuste recurrente (gastos)" },
    { id: 11, mes: "OCT-26", monto: 1742319, desc: "Ajuste recurrente (gastos)" },
    { id: 12, mes: "JUN-27", monto: -72353792, desc: "Pago deuda — Diana" },
    { id: 13, mes: "NOV-27", monto: -72353792, desc: "Pago deuda — Cesar 1" },
    { id: 14, mes: "MAR-28", monto: -72353792, desc: "Pago deuda — Cesar 2" },
    { id: 15, mes: "JUN-28", monto: -345240000, desc: "Pago deuda — Andrés" },
  ]);
  const nextEvId = useRef(16);
  const addEvento = () => {
    setEventosExtra((s) => [...s, { id: nextEvId.current++, mes: "JUL-26", monto: 0, desc: "Nuevo evento" }]);
  };
  const updateEvento = (id, campo, valor) => {
    setEventosExtra((s) => s.map((ev) => (ev.id === id ? { ...ev, [campo]: valor } : ev)));
  };
  const removeEvento = (id) => setEventosExtra((s) => s.filter((ev) => ev.id !== id));

  // ── Overrides de la tabla de caja editable (por mes: gastosFijos, pagoInv) ──
  const [overridesMes, setOverridesMes] = useState({});
  const setOverride = (mes, campo, valor) => {
    setOverridesMes((s) => {
      const next = { ...s, [mes]: { ...(s[mes] || {}) } };
      if (valor == null) {
        delete next[mes][campo];
        if (Object.keys(next[mes]).length === 0) delete next[mes];
      } else {
        next[mes][campo] = valor;
      }
      return next;
    });
  };
  const hayOverrides = Object.keys(overridesMes).length > 0;

  // ── Año a mostrar en los KPIs de caja ("Todos" o un año específico) ──
  const [anioKPI, setAnioKPI] = useState("Todos");

  // ── Datos del Excel validado: cargables desde un archivo real, persistidos entre sesiones ──
  const [cajaExcelData, setCajaExcelData] = useState(CAJA_EXCEL_DEFAULT);
  const [archivoInfo, setArchivoInfo] = useState(null); // { nombre, fecha } del último Excel cargado
  const [cargando, setCargando] = useState(false);
  const [errorCarga, setErrorCarga] = useState(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await window.storage.get("caja_excel_data");
        if (res?.value) setCajaExcelData(JSON.parse(res.value));
        const infoRes = await window.storage.get("caja_excel_info");
        if (infoRes?.value) setArchivoInfo(JSON.parse(infoRes.value));
      } catch (err) { /* aún no hay un Excel guardado — se usan los datos de ejemplo */ }
    })();
  }, []);

  const parseFlujoDeCaja = (workbook) => {
    const nombreHoja = workbook.SheetNames.find((n) => n.trim().toUpperCase() === "FLUJO DE CAJA")
      || workbook.SheetNames.find((n) => n.toUpperCase().includes("FLUJO"));
    if (!nombreHoja) throw new Error('No encontré la hoja "FLUJO DE CAJA" en este archivo.');
    const aoa = XLSX.utils.sheet_to_json(workbook.Sheets[nombreHoja], { header: 1, raw: true, defval: null });
    const fila = (n) => (aoa[n - 1] || []).slice(3); // columnas desde D (mes 1) en adelante
    const header = fila(3);
    const flujoRow = fila(34), cajaRow = fila(35), ingresoRow = fila(21), egresosRow = fila(31), carteraRow = fila(12);
    const data = header
      .map((mes, i) => ({
        mes: mes == null ? "" : String(mes).trim(),
        caja: Math.round(Number(cajaRow[i]) || 0),
        flujo: Math.round(Number(flujoRow[i]) || 0),
        ingresoNeto: Math.round(Number(ingresoRow[i]) || 0),
        egresos: Math.round(Number(egresosRow[i]) || 0),
        cartera: Math.round(Number(carteraRow[i]) || 0),
      }))
      .filter((d) => /^[A-Z]{3}-\d{2}$/.test(d.mes));
    if (!data.length) throw new Error('La hoja "FLUJO DE CAJA" no tiene el formato esperado (fila 3 = meses, fila 35 = Caja acumulada).');
    // motos vendidas por mes desde INVENTARIO (fila 9 = real colocadas, fila 6 = proyectadas)
    const hojaInv = workbook.SheetNames.find((n) => n.trim().toUpperCase() === "INVENTARIO");
    if (hojaInv) {
      const inv = XLSX.utils.sheet_to_json(workbook.Sheets[hojaInv], { header: 1, raw: true, defval: null });
      const f6 = (inv[5] || []).slice(3), f9 = (inv[8] || []).slice(3);
      data.forEach((d, i) => {
        const real = Number(f9[i]) || 0, proy = Number(f6[i]) || 0;
        d.motos = real > 0 ? real : proy;
      });
    }
    return data;
  };

  const handleExcelUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setCargando(true); setErrorCarga(null);
    try {
      const buf = await file.arrayBuffer();
      const wb = XLSX.read(buf, { type: "array" });
      const data = parseFlujoDeCaja(wb);
      const info = { nombre: file.name, fecha: new Date().toLocaleString("es-CO") };
      setCajaExcelData(data);
      setArchivoInfo(info);
      try {
        await window.storage.set("caja_excel_data", JSON.stringify(data), false);
        await window.storage.set("caja_excel_info", JSON.stringify(info), false);
      } catch (err) { console.error("No se pudo guardar el Excel para la próxima sesión:", err); }
    } catch (err) {
      setErrorCarga(err.message || "No pude leer ese archivo. Verifica que sea el Excel del simulador (.xlsx o .xlsm).");
    } finally {
      setCargando(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const restaurarEjemplo = async () => {
    setCajaExcelData(CAJA_EXCEL_DEFAULT);
    setArchivoInfo(null);
    setErrorCarga(null);
    try {
      await window.storage.delete("caja_excel_data");
      await window.storage.delete("caja_excel_info");
    } catch (err) { /* no había nada guardado */ }
  };

  const cajaExcelPorMes = useMemo(
    () => Object.fromEntries(cajaExcelData.map((d) => [d.mes, d])),
    [cajaExcelData]
  );

  // ── Crédito USD en evaluación (p. ej. los USD $3M de Simon) ──
  const [creditoUSD, setCreditoUSD] = useState({
    montoUSD: 3000000, trm: 4200, tasaEA: 0.14, plazoMeses: 60,
    tipo: "FRANCES", desembolso: "2026-09-01", incluir: false,
  });
  const setCred = (k) => (v) => setCreditoUSD((s) => ({ ...s, [k]: v }));
  const creditoCalc = useMemo(() => {
    const montoCOP = (Number(creditoUSD.montoUSD) || 0) * (Number(creditoUSD.trm) || 0);
    const plazo = Math.max(1, Number(creditoUSD.plazoMeses) || 1);
    const venc = mesKeyDesde(creditoUSD.desembolso, plazo);
    const vencIso = venc ? `${venc.anio}-${String(venc.mes).padStart(2, "0")}-01` : creditoUSD.desembolso;
    const calc = calcularCredito({ monto: montoCOP, tasaEA: creditoUSD.tasaEA, tipo: creditoUSD.tipo,
      desembolso: creditoUSD.desembolso, vencimiento: vencIso, cuotaExtra: 0 });
    return { ...calc, montoCOP };
  }, [creditoUSD]);
  const eventosCredito = useMemo(() => {
    if (!creditoUSD.incluir || creditoCalc.montoCOP <= 0) return [];
    const evs = [{ mes: fechaAMesKey(creditoUSD.desembolso), monto: creditoCalc.montoCOP, desc: "Desembolso crédito USD" }];
    for (const row of creditoCalc.rows) if (row.pago > 0) evs.push({ mes: row.key, monto: -row.pago, desc: "Pago crédito USD" });
    return evs;
  }, [creditoUSD, creditoCalc]);

  // ── Comparador de escenarios guardados ──
  const [escenarios, setEscenarios] = useState([]);
  const [nombreEscenario, setNombreEscenario] = useState("");
  const COLORES_ESC = ["#e8b4f8", "#f8d66d", "#7ec8ff", "#ff9e7a"];

  // ── Sensibilidad (se calcula bajo demanda) ──
  const [sensibilidad, setSensibilidad] = useState(null);
  const [calculandoSens, setCalculandoSens] = useState(false);

  // ── Toggle COP/USD para el P&G ──
  const [mostrarUSD, setMostrarUSD] = useState(false);

  const r = useMemo(() => simular(p, [...eventosExtra, ...eventosDeuda, ...eventosCredito], overridesMes), [p, eventosExtra, eventosDeuda, eventosCredito, overridesMes]);
  const chartData = r.rows.map((x) => ({
    mes: x.mes, Caja: x.caja / 1e6, Flujo: x.flujoTotal / 1e6, Cartera: x.cartera,
    "Caja Excel": cajaExcelPorMes[x.mes] ? cajaExcelPorMes[x.mes].caja / 1e6 : null,
    ...Object.fromEntries(escenarios.map((e) => [`💾 ${e.nombre}`, e.serie[x.mes] != null ? e.serie[x.mes] / 1e6 : null])),
    "M. Bruto %": x.margenBrutoPct === null ? null : +(x.margenBrutoPct * 100).toFixed(1),
    "M. Neto %": x.margenNetoPct === null ? null : +(x.margenNetoPct * 100).toFixed(1),
  }));
  const cajaMinExcel = cajaExcelData.reduce((min, d) => (d.caja < min.caja ? d : min), cajaExcelData[0]);

  // ── KPIs por año seleccionado: Excel validado vs proyección del simulador ──
  const anioDeMes = (mes) => 2000 + parseInt(String(mes).slice(-2), 10);
  const aniosDisponibles = useMemo(() => {
    const s = new Set();
    cajaExcelData.forEach((d) => s.add(anioDeMes(d.mes)));
    r.rows.forEach((d) => s.add(anioDeMes(d.mes)));
    return [...s].sort();
  }, [cajaExcelData, r.rows]);
  const excelKPI = anioKPI === "Todos" ? cajaExcelData : cajaExcelData.filter((d) => anioDeMes(d.mes) === anioKPI);
  const simKPI = anioKPI === "Todos" ? r.rows : r.rows.filter((d) => anioDeMes(d.mes) === anioKPI);
  const minDe = (arr) => (arr.length ? arr.reduce((min, d) => (d.caja < min.caja ? d : min), arr[0]) : null);
  const kMinExcel = minDe(excelKPI), kMinSim = minDe(simKPI);
  const kFinExcel = excelKPI.length ? excelKPI[excelKPI.length - 1] : null;
  const kFinSim = simKPI.length ? simKPI[simKPI.length - 1] : null;
  const kCapExcel = kMinExcel ? Math.max(0, p.cajaMinima - kMinExcel.caja) : null;
  const kCapSim = kMinSim ? Math.max(0, p.cajaMinima - kMinSim.caja) : null;
  const kNegExcel = excelKPI.filter((d) => d.caja < 0).length;
  const kCriExcel = excelKPI.filter((d) => d.caja >= 0 && d.caja < p.cajaMinima).length;
  const kNegSim = simKPI.filter((d) => d.caja < 0).length;
  const kCriSim = simKPI.filter((d) => d.caja >= 0 && d.caja < p.cajaMinima).length;
  const kCartExcel = excelKPI.reduce((mx, d) => Math.max(mx, d.cartera), 0);
  const kCartSim = simKPI.reduce((mx, d) => Math.max(mx, d.cartera), 0);
  const hayMotosExcel = excelKPI.some((d) => d.motos != null);
  const kMotosExcel = excelKPI.reduce((s, d) => s + (Number(d.motos) || 0), 0);
  const kMotosSim = simKPI.reduce((s, d) => s + (Number(d.motos) || 0), 0);

  // ── Escenarios: guardar / eliminar la serie de caja actual ──
  const guardarEscenario = () => {
    if (escenarios.length >= 4) return;
    const nombre = nombreEscenario.trim() || `Escenario ${escenarios.length + 1}`;
    setEscenarios((s) => [...s, { id: Date.now(), nombre,
      serie: Object.fromEntries(r.rows.map((x) => [x.mes, x.caja])) }]);
    setNombreEscenario("");
  };
  const eliminarEscenario = (id) => setEscenarios((s) => s.filter((e) => e.id !== id));

  // ── Sensibilidad y punto de equilibrio (bajo demanda: ~20 simulaciones) ──
  const calcularSensibilidad = () => {
    setCalculandoSens(true);
    setTimeout(() => {
      const evs = [...eventosExtra, ...eventosDeuda, ...eventosCredito];
      const baseMin = simular(p, evs, overridesMes).minCaja;
      const vars = [
        { label: "Motos / mes", key: "motosMes", delta: 0.2 },
        { label: "Cuota Raider", key: "cuotaRaider", delta: 0.1 },
        { label: "Gastos fijos", key: "gastosFijos", delta: 0.1 },
        { label: "% Mora", key: "pctMora", delta: 0.5 },
        { label: "Costo moto (Auteco)", key: "costoRaider", delta: 0.1 },
      ];
      const res = vars.map((v) => ({
        ...v,
        up: simular({ ...p, [v.key]: p[v.key] * (1 + v.delta) }, evs, overridesMes).minCaja - baseMin,
        dn: simular({ ...p, [v.key]: p[v.key] * (1 - v.delta) }, evs, overridesMes).minCaja - baseMin,
      })).sort((a, b) => Math.max(Math.abs(b.up), Math.abs(b.dn)) - Math.max(Math.abs(a.up), Math.abs(a.dn)));
      // punto de equilibrio: mínimo de motos/mes sin ningún mes de caja negativa
      const negativos = (m) => simular({ ...p, motosMes: m }, evs, overridesMes).mesesNegativos;
      let lo = 0, hi = Math.max(10, p.motosMes);
      while (negativos(hi) > 0 && hi < p.motosMes * 5) hi *= 2;
      let eq = negativos(hi) > 0 ? null : hi;
      if (eq !== null) {
        let a = lo, b = hi;
        while (a <= b) { const mid = Math.floor((a + b) / 2); if (negativos(mid) === 0) { eq = mid; b = mid - 1; } else a = mid + 1; }
      }
      setSensibilidad({ baseMin, res, equilibrio: eq, motosBase: p.motosMes });
      setCalculandoSens(false);
    }, 30);
  };

  // ── Cuota ponderada de la deuda: servicio mensual total y tasa EA ponderada por monto ──
  // (declarada aquí porque indicadoresAnio la necesita más abajo)
  const deudaActiva = inversionistas.filter((inv) => inv.estado === "Activo");
  const cuotaMensualPonderada = deudaActiva.reduce((s, inv) => {
    const c = calcularCredito(inv);
    return s + (c.tipo === "BULLET_VENC" ? 0 : c.cuotaBase + c.extra);
  }, 0);
  const pagoUnicoVencimientos = deudaActiva.reduce((s, inv) => {
    const c = calcularCredito(inv);
    return s + (c.tipo === "BULLET_VENC" ? c.totPagado : 0);
  }, 0);
  const totalDeudaActiva = deudaActiva.reduce((s, inv) => s + (Number(inv.monto) || 0), 0);
  const tasaEAPonderada = totalDeudaActiva > 0
    ? deudaActiva.reduce((s, inv) => s + (Number(inv.monto) || 0) * (Number(inv.tasaEA) || 0), 0) / totalDeudaActiva
    : 0;

  // ── Indicadores de crédito por año (DSCR y apalancamiento) ──
  const saldoCredUSDFinDeAnio = (a) => {
    if (!creditoUSD.incluir) return 0;
    const rowsA = creditoCalc.rows.filter((rr) => rr.anio === a);
    if (rowsA.length) return Math.max(0, rowsA[rowsA.length - 1].saldo);
    const yDes = Number(String(creditoUSD.desembolso).slice(0, 4));
    const yFin = creditoCalc.rows.length ? creditoCalc.rows[creditoCalc.rows.length - 1].anio : yDes;
    return a >= yDes && a < yFin ? creditoCalc.montoCOP : 0;
  };
  const indicadoresAnio = useMemo(() => {
    const anios = [...new Set(r.rows.map((x) => x.anio))];
    return anios.map((a) => {
      const rowsA = r.rows.filter((x) => x.anio === a);
      const flujoA = rowsA.reduce((s, x) => s + x.flujoTotal, 0);
      const servicioCred = creditoUSD.incluir
        ? creditoCalc.rows.filter((rr) => rr.anio === a).reduce((s, rr) => s + rr.pago, 0) : 0;
      const pagosUnicos = inversionistas
        .filter((iv) => iv.estado === "Activo" && iv.tipo === "BULLET_VENC" && Number(String(iv.vencimiento).slice(0, 4)) === a)
        .reduce((s, iv) => s + calcularCredito(iv).totPagado, 0);
      const servicio = cuotaMensualPonderada * rowsA.length + servicioCred + pagosUnicos;
      const dscr = servicio > 0 ? (flujoA + servicio) / servicio : null;
      const fin = rowsA[rowsA.length - 1];
      const deudaFin = totalDeudaActiva + saldoCredUSDFinDeAnio(a);
      const cajaMinA = rowsA.reduce((mn, x) => Math.min(mn, x.caja), Infinity);
      return {
        anio: a, flujoA, servicio, dscr,
        deudaCartera: fin && fin.cxc > 0 ? deudaFin / fin.cxc : null,
        deudaPatrimonio: fin && fin.patrimonio > 0 ? deudaFin / fin.patrimonio : null,
        cajaMinA,
      };
    });
  }, [r, creditoUSD, creditoCalc, inversionistas, cuotaMensualPonderada, totalDeudaActiva]);

  // ── P&G anual ──
  const pygAnual = useMemo(() => {
    const anios = [...new Set(r.rows.map((x) => x.anio))];
    return anios.map((a) => {
      const rowsA = r.rows.filter((x) => x.anio === a);
      const sum = (f) => rowsA.reduce((s, x) => s + f(x), 0);
      const ingresos = sum((x) => x.neto);
      const utilidad = sum((x) => x.utilidad);
      return {
        anio: a, meses: rowsA.length, ingresos,
        costoLotes: -sum((x) => x.loteBruto),
        gastos: sum((x) => x.gastosFijos),
        gps: sum((x) => x.gps),
        financiero: sum((x) => x.intDeuda + x.fondeo),
        utilidad, margen: ingresos > 0 ? utilidad / ingresos : null,
      };
    });
  }, [r]);
  const fmtMoneda = (v) => (mostrarUSD ? `US$ ${((v || 0) / (Number(creditoUSD.trm) || 1)).toLocaleString("es-CO", { maximumFractionDigits: 0 })}` : fmtInt(v));

  // ── Exportación a Excel (flujo mensual + P&G anual + indicadores) ──
  const exportarExcel = () => {
    const wb = XLSX.utils.book_new();
    const flujoData = r.rows.map((x) => ({
      Mes: x.mes, Motos: x.motos, Cartera: x.cartera,
      "Ingreso neto": Math.round(x.neto), "Gastos fijos": Math.round(x.gastosFijos),
      GPS: Math.round(x.gps), "Costo motos nuevas": Math.round(x.costoNueva),
      "Adelanto Auteco": Math.round(x.adelanto), "Pago inventario Auteco": Math.round(x.pagoInv),
      "Fondeo Auteco": Math.round(x.fondeo), "Int. deuda": Math.round(x.intDeuda),
      "Eventos + deuda": Math.round(x.extra + x.inyeccion),
      "Flujo neto": Math.round(x.flujoTotal), "Caja acumulada": Math.round(x.caja),
      "Caja Excel (ref.)": cajaExcelPorMes[x.mes] ? Math.round(cajaExcelPorMes[x.mes].caja) : null,
    }));
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(flujoData), "FLUJO CAJA");
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(pygAnual.map((y) => ({
      "Año": y.anio, Meses: y.meses, "Ingresos netos": Math.round(y.ingresos),
      "Costo lotes (motos)": Math.round(y.costoLotes), "Gastos fijos": Math.round(y.gastos),
      GPS: Math.round(y.gps), Financiero: Math.round(y.financiero),
      Utilidad: Math.round(y.utilidad), "Margen neto %": y.margen != null ? +(y.margen * 100).toFixed(1) : null,
    }))), "PYG ANUAL");
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(indicadoresAnio.map((y) => ({
      "Año": y.anio, "Flujo neto anual": Math.round(y.flujoA), "Servicio de deuda": Math.round(y.servicio),
      DSCR: y.dscr != null ? +y.dscr.toFixed(2) : null,
      "Deuda/Cartera": y.deudaCartera != null ? +y.deudaCartera.toFixed(2) : null,
      "Caja mínima del año": Math.round(y.cajaMinA),
    }))), "INDICADORES");
    XLSX.writeFile(wb, "RODDOS_Proyeccion.xlsx");
  };


  const escMora = (esc) => {
    if (esc === "P") setP((s) => ({ ...s, pctMora: 0.06, pctRecuperacion: 0.30 }));
    if (esc === "B") setP((s) => ({ ...s, pctMora: 0.03, pctRecuperacion: 0.40 }));
    if (esc === "O") setP((s) => ({ ...s, pctMora: 0.015, pctRecuperacion: 0.60 }));
  };

  const ultimoAnioCompleto = [...r.porAnio].reverse().find((a) => a.n === 12) || r.porAnio[r.porAnio.length - 1];

  // ── Ingresos: real vs. proyectado ──
  const ingresosChartData = r.rows.map((x, i) => ({
    mes: x.mes,
    Proyectado: +(x.neto / 1e6).toFixed(1),
    Real: ingresosReales[i] == null ? null : +(ingresosReales[i] / 1e6).toFixed(1),
  }));
  const mesesConIngresoReal = r.rows.map((_, i) => i).filter((i) => ingresosReales[i] != null);
  const ingresoRealAcum = mesesConIngresoReal.reduce((s, i) => s + ingresosReales[i], 0);
  const ingresoProyComparable = mesesConIngresoReal.reduce((s, i) => s + r.rows[i].neto, 0);
  const desviacionIngresoPct = ingresoProyComparable > 0 ? (ingresoRealAcum - ingresoProyComparable) / ingresoProyComparable : null;

  // ── Presupuesto vs. ejecutado (gastos fijos) ──
  const gastosChartData = r.rows.map((x, i) => ({
    mes: x.mes,
    Presupuestado: +(p.gastosFijos / 1e6).toFixed(1),
    Ejecutado: gastosReales[i] == null ? null : +(gastosReales[i] / 1e6).toFixed(1),
  }));
  const mesesConGastoReal = r.rows.map((_, i) => i).filter((i) => gastosReales[i] != null);
  const gastoRealAcum = mesesConGastoReal.reduce((s, i) => s + gastosReales[i], 0);
  const gastoPresupuestadoComparable = mesesConGastoReal.length * p.gastosFijos;
  const desviacionGastoPct = gastoPresupuestadoComparable > 0 ? (gastoRealAcum - gastoPresupuestadoComparable) / gastoPresupuestadoComparable : null;

  // ── Deuda con inversionistas (real) ──
  const totalInversionistas = inversionistas.reduce((s, inv) => s + (Number(inv.monto) || 0), 0);
  const difiereDelModelo = Math.abs(totalInversionistas - p.deuda) > 1;
  const HOY = new Date("2026-07-02");
  const proximosVencimientos = [...inversionistas]
    .map((inv) => ({ ...inv, dias: Math.round((new Date(inv.vencimiento) - HOY) / 86400000) }))
    .filter((inv) => inv.estado === "Activo" && inv.dias >= -30)
    .sort((a, b) => a.dias - b.dias);


  return (
    <div style={{
      minHeight: "100vh", background: C.bg, color: C.text,
      fontFamily: "'Segoe UI', system-ui, -apple-system, sans-serif", padding: 18,
    }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 4, flexWrap: "wrap" }}>
        <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: ".02em" }}>
          RODDOS<span style={{ color: C.green }}>.</span>
        </div>
        <div style={{ fontSize: 13, color: C.dim }}>Simulador financiero · cartera de motos · MAY-26 → DIC-40 · v6 (escenario 50 motos/mes +1% mensual, validado contra Modelo_Financiero_LoanTape_Modificado.xlsm hasta DIC-30)</div>
      </div>
      <div style={{ fontSize: 11.5, color: C.dim, marginBottom: 14 }}>
        Motor que replica la macro SimularVentas y la hoja FLUJO DE CAJA del Excel LoanTape: cohortes por miércoles reales, cartera previa de 111 créditos con su recaudo semanal REAL (incluye moras), lote Auteco con split fraccionario 70/30, pago de lotes con saldo rodante (5 meses, neto de adelantos), fondeo 1,6%/mes e intereses de deuda JUL-26→JUN-27. Arranca en MAY-26 con caja fija de {fmtM(24000000)} y ventas de 50 motos/mes desde JUL-26 creciendo 1% mensual encadenado (50, 51, 52… como la columna C del SIMULADOR). Verificado mes a mes contra el Excel hasta DIC-30 (diferencia máxima $20,9 M, &lt; 0,2%); de ENE-31 a DIC-40 la proyección extiende la misma mecánica. Incluye P&G devengado y balance aproximado para ROE, ROA y WACC.
      </div>

      {/* Carga de Excel actualizado */}
      <div style={{
        display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
        background: C.card, border: `1px solid ${C.turq}55`, borderRadius: 10,
        padding: "10px 14px", marginBottom: 16,
      }}>
        <input ref={fileInputRef} type="file" accept=".xlsx,.xlsm,.xls" onChange={handleExcelUpload}
               style={{ display: "none" }} />
        <button onClick={() => fileInputRef.current?.click()} disabled={cargando} style={{
          background: C.turq, border: "none", borderRadius: 6, color: "#04211f",
          padding: "7px 14px", cursor: cargando ? "default" : "pointer", fontSize: 12.5, fontWeight: 700,
          opacity: cargando ? 0.6 : 1,
        }}>
          {cargando ? "Leyendo archivo…" : "📥 Cargar Excel actualizado"}
        </button>
        <div style={{ fontSize: 11.5, color: C.dim, lineHeight: 1.4 }}>
          {archivoInfo ? (
            <>Usando <b style={{ color: C.text }}>{archivoInfo.nombre}</b> · cargado el {archivoInfo.fecha}</>
          ) : (
            <>Mostrando datos de ejemplo. Sube tu archivo (hoja "FLUJO DE CAJA") para reemplazarlos por tus cifras reales.</>
          )}
        </div>
        {archivoInfo && (
          <button onClick={restaurarEjemplo} style={{
            background: "none", border: `1px solid ${C.border}`, borderRadius: 6, color: C.dim,
            padding: "5px 10px", cursor: "pointer", fontSize: 11.5,
          }}>Restaurar ejemplo</button>
        )}
        {errorCarga && <div style={{ fontSize: 11.5, color: C.red, width: "100%" }}>⚠ {errorCarga}</div>}
      </div>

      {/* KPIs de caja — Excel validado vs proyección, con selector de año */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 6 }}>
        <div style={{ fontSize: 11, color: C.dim, letterSpacing: ".07em", textTransform: "uppercase" }}>
          Caja · Excel validado vs proyección del simulador
        </div>
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {["Todos", ...aniosDisponibles].map((a) => (
            <button key={a} onClick={() => setAnioKPI(a)} style={{
              background: anioKPI === a ? C.turq : C.card2,
              border: `1px solid ${anioKPI === a ? C.turq : C.border}`,
              borderRadius: 6, color: anioKPI === a ? "#04211f" : C.dim,
              padding: "3px 10px", cursor: "pointer", fontSize: 11,
              fontWeight: anioKPI === a ? 700 : 400,
            }}>{a}</button>
          ))}
        </div>
      </div>
      <div style={{ fontSize: 10.5, color: C.dim, letterSpacing: ".05em", marginBottom: 4 }}>
        📊 EXCEL VALIDADO (referencia)
      </div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 10 }}>
        <KPI label={`Caja mínima${anioKPI === "Todos" ? "" : ` ${anioKPI}`}`}
             value={kMinExcel ? fmtM(kMinExcel.caja) : "—"}
             sub={kMinExcel ? `en ${kMinExcel.mes}` : "sin datos Excel"}
             tone={kMinExcel ? (kMinExcel.caja < 0 ? "bad" : kMinExcel.caja < p.cajaMinima ? "warn" : "good") : undefined} />
        <KPI label={`Caja final${anioKPI === "Todos" ? "" : ` ${anioKPI}`}`}
             value={kFinExcel ? fmtM(kFinExcel.caja) : "—"}
             sub={kFinExcel ? kFinExcel.mes : "sin datos Excel"}
             tone={kFinExcel ? (kFinExcel.caja < 0 ? "bad" : "good") : undefined} />
        <KPI label="Capital requerido"
             value={kCapExcel != null ? fmtM(kCapExcel) : "—"}
             sub={kCapExcel > 0 ? "para no bajar de caja mínima" : "sin brecha de caja"}
             tone={kCapExcel > 0 ? "warn" : "good"} />
        <KPI label="Cartera pico"
             value={excelKPI.length ? kCartExcel.toLocaleString("es-CO") : "—"}
             sub="créditos activos" />
        <KPI label="Motos vendidas"
             value={hayMotosExcel ? kMotosExcel.toLocaleString("es-CO") : "—"}
             sub={anioKPI === "Todos" ? "horizonte completo" : `año ${anioKPI}`} />
        <KPI label="Meses críticos / negativos"
             value={excelKPI.length ? `${kCriExcel} / ${kNegExcel}` : "—"}
             sub={anioKPI === "Todos" ? "horizonte completo" : `año ${anioKPI}`}
             tone={kNegExcel > 0 ? "bad" : kCriExcel > 0 ? "warn" : "good"} />
      </div>

      <div style={{ fontSize: 10.5, color: C.dim, letterSpacing: ".05em", marginBottom: 4 }}>
        🔮 CAJA PROYECTADA (simulador del dashboard)
      </div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 6 }}>
        <KPI label={`Caja mínima${anioKPI === "Todos" ? "" : ` ${anioKPI}`}`}
             value={kMinSim ? fmtM(kMinSim.caja) : "—"}
             sub={kMinSim ? `en ${kMinSim.mes}` : "—"}
             tone={kMinSim ? (kMinSim.caja < 0 ? "bad" : kMinSim.caja < p.cajaMinima ? "warn" : "good") : undefined} />
        <KPI label={`Caja final${anioKPI === "Todos" ? "" : ` ${anioKPI}`}`}
             value={kFinSim ? fmtM(kFinSim.caja) : "—"}
             sub={kFinSim ? kFinSim.mes : "—"}
             tone={kFinSim ? (kFinSim.caja < 0 ? "bad" : "good") : undefined} />
        <KPI label="Capital requerido"
             value={kCapSim != null ? fmtM(kCapSim) : "—"}
             sub={kCapSim > 0 ? "para no bajar de caja mínima" : "sin brecha de caja"}
             tone={kCapSim > 0 ? "warn" : "good"} />
        <KPI label="Cartera pico"
             value={kCartSim.toLocaleString("es-CO")}
             sub="créditos activos" />
        <KPI label="Motos vendidas"
             value={kMotosSim.toLocaleString("es-CO")}
             sub={anioKPI === "Todos" ? "horizonte completo" : `año ${anioKPI}`} />
        <KPI label="Meses críticos / negativos"
             value={`${kCriSim} / ${kNegSim}`}
             sub={anioKPI === "Todos" ? "horizonte completo" : `año ${anioKPI}`}
             tone={kNegSim > 0 ? "bad" : kCriSim > 0 ? "warn" : "good"} />
        <KPI label="Costo fondeo Auteco" value={fmtM(r.totFondeo)} sub="acumulado horizonte" tone="warn" />
      </div>
      <div style={{ fontSize: 10.5, color: C.dim, marginBottom: 14, lineHeight: 1.5 }}>
        La fila superior es el Excel validado (referencia fija); la inferior es la proyección del simulador con los supuestos, eventos y celdas editadas actuales. En el escenario base ambas coinciden (&lt; 0,1% de diferencia); al cambiar cualquier supuesto, la fila proyectada se separa y puedes comparar contra la referencia, año por año con los botones de arriba.
      </div>


      {/* KPIs de rentabilidad */}
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 14 }}>
        <KPI label={`ROE ${ultimoAnioCompleto?.anio ?? ""}`} value={fmtPct(ultimoAnioCompleto?.roe)}
             sub="utilidad anualizada / patrimonio prom." tone={(ultimoAnioCompleto?.roe ?? 0) > 0 ? "good" : "bad"} />
        <KPI label={`ROA ${ultimoAnioCompleto?.anio ?? ""}`} value={fmtPct(ultimoAnioCompleto?.roa)}
             sub="utilidad anualizada / activos prom." tone={(ultimoAnioCompleto?.roa ?? 0) > 0 ? "good" : "bad"} />
        <KPI label="WACD" value={fmtPct(r.wacd)} sub="costo ponderado de deuda (EA)" tone="warn" />
        <KPI label="WACC" value={fmtPct(r.wacc)} sub={`Ke ${fmtPct(p.ke,0)} · imp. ${fmtPct(p.tasaImpuestos,0)}`} />
        <KPI label="Utilidad acumulada" value={fmtM(r.utilidadAcum)} sub="P&G devengado del horizonte"
             tone={r.utilidadAcum > 0 ? "good" : "bad"} />
        <KPI label={`Margen neto ${ultimoAnioCompleto?.anio ?? ""}`} value={fmtPct(ultimoAnioCompleto?.margen)}
             sub="utilidad / ingreso neto" />
        <KPI label="Margen bruto estabilizado" value={fmtPct(r.rows[r.rows.length-1]?.margenBrutoPct)}
             sub={`${r.rows[r.rows.length-1]?.mes} · sin GPS`} tone="good" />
      </div>

      {/* KPIs reales vs. modelo */}
      <div style={{ fontSize: 11, color: C.dim, letterSpacing: ".07em", textTransform: "uppercase", marginBottom: 6 }}>
        Datos reales cargados · comparación vs. modelo
      </div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 14 }}>
        <KPI label="Ingreso real acum." value={fmtM(ingresoRealAcum)}
             sub={desviacionIngresoPct == null ? `${mesesConIngresoReal.length} meses cargados` : `${fmtPct(desviacionIngresoPct)} vs. proyectado`}
             tone={desviacionIngresoPct == null ? undefined : desviacionIngresoPct >= 0 ? "good" : "bad"} />
        <KPI label="Ejecutado real acum." value={fmtM(gastoRealAcum)}
             sub={desviacionGastoPct == null ? `${mesesConGastoReal.length} meses cargados` : `${fmtPct(desviacionGastoPct)} vs. presupuesto`}
             tone={desviacionGastoPct == null ? undefined : desviacionGastoPct <= 0 ? "good" : "warn"} />
        <KPI label="Deuda inversionistas (real)" value={fmtM(totalInversionistas)}
             sub={difiereDelModelo ? `modelo usa ${fmtM(p.deuda)}` : "= parámetro del modelo"}
             tone={difiereDelModelo ? "warn" : "good"} />
        <KPI label="Próx. vencimiento inversionista" value={proximosVencimientos[0] ? `${proximosVencimientos[0].dias} d` : "—"}
             sub={proximosVencimientos[0]?.nombre ?? "sin vencimientos activos"}
             tone={proximosVencimientos[0] && proximosVencimientos[0].dias <= 60 ? "warn" : undefined} />
      </div>

      <div style={{ display: "flex", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
        {/* Panel de control */}
        <div style={{
          flex: "0 0 260px", minWidth: 240, background: C.card,
          border: `1px solid ${C.border}`, borderRadius: 12, padding: "4px 14px 10px",
        }}>
          <Seccion titulo="Ventas" abierta={sec.ventas} onToggle={tg("ventas")}>
            <Num label="Motos por mes" value={p.motosMes} onChange={set("motosMes")} min={0} step={5} />
            <Num label="Crecimiento mensual" value={p.crecMensual} onChange={set("crecMensual")} step={0.5} suffix="%" />
            <Num label="% Apache (resto Raider)" value={Math.round(p.pctApache*100)} onChange={(v)=>set("pctApache")(v/100)} step={5} suffix="%" min={0} max={100} />
            <Num label="Plazo del crédito" value={p.plazoSemanas} onChange={set("plazoSemanas")} step={26} suffix="sem" />
          </Seccion>
          <Seccion titulo="Producto" abierta={sec.producto} onToggle={tg("producto")}>
            <Num label="Cuota semanal Raider" value={p.cuotaRaider} onChange={set("cuotaRaider")} step={5000} suffix="COP" hint="corregida" />
            <Num label="Cuota semanal Apache" value={p.cuotaApache} onChange={set("cuotaApache")} step={5000} suffix="COP" />
            <Num label="Cuota inicial Raider" value={p.iniRaider} onChange={set("iniRaider")} step={50000} suffix="COP" />
            <Num label="Cuota inicial Apache" value={p.iniApache} onChange={set("iniApache")} step={50000} suffix="COP" />
            <Num label="Costo Auteco Raider" value={p.costoRaider} onChange={set("costoRaider")} step={50000} suffix="COP" />
            <Num label="Costo Auteco Apache" value={p.costoApache} onChange={set("costoApache")} step={50000} suffix="COP" />
          </Seccion>
          <Seccion titulo="Fondeo Auteco" abierta={sec.auteco} onToggle={tg("auteco")}>
            <Num label="Plazo pago inventario" value={p.plazoAutecoDias} onChange={set("plazoAutecoDias")} step={30} suffix="días" />
            <Num label="Días base sin costo" value={p.baseAutecoDias} onChange={set("baseAutecoDias")} step={30} suffix="días" />
            <Num label="Tasa por mes adicional" value={+(p.tasaAuteco*100).toFixed(2)} onChange={(v)=>set("tasaAuteco")(v/100)} step={0.1} suffix="%/mes" hint="confirmada 1,6%" />
            <Num label="Adelanto por moto" value={p.adelantoAuteco} onChange={set("adelantoAuteco")} step={10000} suffix="COP" />
          </Seccion>
          <Seccion titulo="Mora y riesgo" abierta={sec.mora} onToggle={tg("mora")}>
            <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
              {[["P","Pesimista"],["B","Base"],["O","Optimista"]].map(([k,n]) => (
                <button key={k} onClick={() => escMora(k)} style={{
                  flex: 1, background: C.card2, border: `1px solid ${C.border}`, borderRadius: 6,
                  color: C.text, padding: "5px 0", fontSize: 11, cursor: "pointer",
                }}>{n}</button>
              ))}
            </div>
            <Num label="% Mora" value={+(p.pctMora*100).toFixed(1)} onChange={(v)=>set("pctMora")(v/100)} step={0.5} suffix="%" />
            <Num label="% Recuperación mora" value={+(p.pctRecuperacion*100).toFixed(0)} onChange={(v)=>set("pctRecuperacion")(v/100)} step={5} suffix="%" />
            <Num label="% Default" value={+(p.pctDefault*100).toFixed(1)} onChange={(v)=>set("pctDefault")(v/100)} step={0.5} suffix="%" />
            <Num label="% Provisión" value={+(p.pctProvision*100).toFixed(1)} onChange={(v)=>set("pctProvision")(v/100)} step={0.5} suffix="%" />
          </Seccion>
          <Seccion titulo="Operación" abierta={sec.opex} onToggle={tg("opex")}>
            <Num label="Gastos fijos / mes" value={p.gastosFijos} onChange={set("gastosFijos")} step={1000000} suffix="COP"
                 hint="Vinculado a la Hoja GASTOS (panel de resultados): el total de los rubros sobrescribe este valor al editarlos." />
            <Num label="GPS por moto activa / mes" value={p.gpsMoto} onChange={set("gpsMoto")} step={1000} suffix="COP" />
            <Num label="Costo por moto nueva" value={p.costoMotoNueva} onChange={set("costoMotoNueva")} step={10000} suffix="COP" hint="GPS+SOAT+matrícula" />
          </Seccion>
          <Seccion titulo="Capital y deuda" abierta={sec.capital} onToggle={tg("capital")}>
            <Num label="Caja inicial (JUL-26)" value={p.cajaInicial} onChange={set("cajaInicial")} step={10000000} suffix="COP" />
            <Num label="Caja mínima requerida" value={p.cajaMinima} onChange={set("cajaMinima")} step={5000000} suffix="COP" />
            <Num label="Inyección de capital" value={p.inyeccion} onChange={set("inyeccion")} step={100000000} suffix="COP" hint="USD 3M ≈ 12.600 M" />
            <Num label="Mes de inyección (0 = JUL-26)" value={p.mesInyeccion} onChange={set("mesInyeccion")} step={1} min={0} max={p.horizonteMeses-1} />
            <Num label="Deuda inversores" value={p.deuda} onChange={set("deuda")} step={10000000} suffix="COP" />
            <Num label="Tasa deuda inversores" value={+(p.tasaDeuda*100).toFixed(2)} onChange={(v)=>set("tasaDeuda")(v/100)} step={0.1} suffix="%/mes" />
            <Num label="Meses pago intereses" value={p.mesesDeuda} onChange={set("mesesDeuda")} step={1} min={0} />
          </Seccion>
          <Seccion titulo="Indicadores (ROE · ROA · WACC)" abierta={sec.indicadores} onToggle={tg("indicadores")}>
            <Num label="Costo del equity (Ke)" value={+(p.ke*100).toFixed(1)} onChange={(v)=>set("ke")(v/100)} step={1} suffix="% EA" hint="retorno exigido por socios" />
            <Num label="Tasa impositiva" value={+(p.tasaImpuestos*100).toFixed(0)} onChange={(v)=>set("tasaImpuestos")(v/100)} step={1} suffix="%" hint="renta Colombia 35%" />
          </Seccion>
        </div>

        {/* Resultados */}
        <div style={{ flex: "1 1 560px", minWidth: 340, display: "flex", flexDirection: "column", gap: 14 }}>

          {/* Hoja GASTOS — vinculada al parámetro Gastos fijos */}
          <div style={{ background: C.card, border: `1px solid ${C.turq}55`, borderRadius: 12, padding: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
              <div style={{ fontSize: 11, color: C.dim, letterSpacing: ".07em", textTransform: "uppercase" }}>
                🧾 Hoja GASTOS · presupuesto de gastos fijos (vinculada al modelo)
              </div>
              <div style={{ fontSize: 12 }}>
                Total: <b style={{ color: C.turqSoft, fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>{fmtM(totalGastosDetalle)}/mes</b>
                <span style={{ fontSize: 11, color: C.greenSoft, marginLeft: 8 }}>✓ sincronizado con "Gastos fijos / mes"</span>
              </div>
            </div>
            <div style={{ fontSize: 11, color: C.dim, margin: "6px 0 8px", lineHeight: 1.5 }}>
              Los 42 rubros de la hoja GASTOS del Excel. Edita cualquier monto, agrega o elimina rubros y el total actualiza automáticamente el parámetro "Gastos fijos / mes" del panel de Operación — el flujo de caja proyectado, los KPIs y la tabla de caja se recalculan al instante.
            </div>
            <button onClick={() => setVerHojaGastos(!verHojaGastos)} style={{
              background: "none", border: `1px solid ${C.border}`, borderRadius: 6,
              color: C.turqSoft, padding: "6px 14px", cursor: "pointer", fontSize: 12,
            }}>
              {verHojaGastos ? "Ocultar rubros" : `Ver / editar los ${gastosDetalle.length} rubros`}
            </button>
            {verHojaGastos && (() => {
              const categorias = [...new Set(gastosDetalle.map((g) => g.cat))];
              return (
                <div style={{ marginTop: 10 }}>
                  <div style={{ overflowX: "auto", maxHeight: 420, overflowY: "auto" }}>
                    <table style={{ borderCollapse: "collapse", fontSize: 11.5, width: "100%", minWidth: 520 }}>
                      <thead>
                        <tr style={{ color: C.dim }}>
                          {["Categoría","Descripción","Valor mensual",""].map((h,i)=>(
                            <th key={h} style={{ padding: "4px 8px", borderBottom: `1px solid ${C.border}`,
                                                 textAlign: i===2?"right":i===3?"center":"left", whiteSpace: "nowrap",
                                                 position: "sticky", top: 0, background: C.card, zIndex: 1 }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {categorias.map((cat) => {
                          const rubros = gastosDetalle.filter((g) => g.cat === cat);
                          const subtotal = rubros.reduce((s, g) => s + (Number(g.monto) || 0), 0);
                          return [
                            ...rubros.map((g) => (
                              <tr key={g.id}>
                                <td style={{ padding: "3px 6px" }}>
                                  <input value={g.cat} onChange={(e) => updateGasto(g.id, "cat", e.target.value)}
                                    style={{ width: 130, background: C.card2, border: `1px solid ${C.border}`, borderRadius: 5, color: C.dim, padding: "3px 6px", fontSize: 10.5 }} />
                                </td>
                                <td style={{ padding: "3px 6px" }}>
                                  <input value={g.desc} onChange={(e) => updateGasto(g.id, "desc", e.target.value)}
                                    style={{ width: "100%", minWidth: 170, background: C.card2, border: `1px solid ${C.border}`, borderRadius: 5, color: C.text, padding: "3px 6px", fontSize: 11.5 }} />
                                </td>
                                <td style={{ padding: "3px 6px", textAlign: "right" }}>
                                  <MontoInput value={Math.round(g.monto)} onChange={(n) => updateGasto(g.id, "monto", n)} width={104} />
                                </td>
                                <td style={{ padding: "3px 6px", textAlign: "center" }}>
                                  <button onClick={() => removeGasto(g.id)} title="Eliminar rubro"
                                    style={{ background: "none", border: `1px solid ${C.border}`, borderRadius: 5, color: C.red, cursor: "pointer", padding: "2px 8px", fontSize: 12 }}>×</button>
                                </td>
                              </tr>
                            )),
                            <tr key={`sub-${cat}`} style={{ background: `${C.card2}88` }}>
                              <td colSpan={2} style={{ padding: "3px 8px", color: C.dim, fontSize: 10.5, textAlign: "right" }}>Total {cat}</td>
                              <td style={{ padding: "3px 8px", textAlign: "right", color: C.turqSoft, fontWeight: 700,
                                           fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>{fmtInt(subtotal)}</td>
                              <td />
                            </tr>,
                          ];
                        })}
                        <tr>
                          <td colSpan={2} style={{ padding: "6px 8px", textAlign: "right", fontWeight: 800, borderTop: `1px solid ${C.border}` }}>
                            TOTAL GASTOS FIJOS MENSUALES
                          </td>
                          <td style={{ padding: "6px 8px", textAlign: "right", fontWeight: 800, color: C.greenSoft, borderTop: `1px solid ${C.border}`,
                                       fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>{fmtInt(totalGastosDetalle)}</td>
                          <td style={{ borderTop: `1px solid ${C.border}` }} />
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <button onClick={addGasto} style={{
                    background: "none", border: `1px solid ${C.border}`, borderRadius: 6,
                    color: C.turqSoft, padding: "6px 14px", cursor: "pointer", fontSize: 12, marginTop: 10,
                  }}>+ Agregar rubro</button>
                </div>
              );
            })()}
          </div>

          {/* Eventos extraordinarios de caja */}
          <div style={{ background: C.card, border: `1px solid ${C.turq}55`, borderRadius: 12, padding: 14 }}>
            <div style={{ fontSize: 11, color: C.dim, letterSpacing: ".07em", textTransform: "uppercase", marginBottom: 4 }}>
              ⚡ Eventos extraordinarios de caja (hallados en el Excel validado)
            </div>
            <div style={{ fontSize: 11, color: C.dim, marginBottom: 8, lineHeight: 1.5 }}>
              Financiación, pagos puntuales y deuda con terceros que el motor de ventas no puede derivar por sí solo. Edítalos o agrega nuevos si cambian.
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ borderCollapse: "collapse", fontSize: 11.5, width: "100%", minWidth: 520 }}>
                <thead>
                  <tr style={{ color: C.dim }}>
                    {["Mes","Monto","Descripción",""].map((h,i)=>(
                      <th key={h} style={{ padding: "4px 8px", borderBottom: `1px solid ${C.border}`,
                                           textAlign: i===0?"left":i===3?"center":"right", whiteSpace: "nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {eventosExtra.map((ev) => (
                    <tr key={ev.id}>
                      <td style={{ padding: "3px 6px" }}>
                        <select value={ev.mes} onChange={(e) => updateEvento(ev.id, "mes", e.target.value)}
                          style={{ background: C.card2, border: `1px solid ${C.border}`, borderRadius: 5, color: C.text, padding: "3px 6px", fontSize: 11 }}>
                          {r.rows.map((x) => <option key={x.mes} value={x.mes}>{x.mes}</option>)}
                        </select>
                      </td>
                      <td style={{ padding: "3px 6px", textAlign: "right" }}>
                        <MontoInput value={ev.monto} onChange={(n) => updateEvento(ev.id, "monto", n)} width={120}
                          style={{ color: ev.monto >= 0 ? C.greenSoft : C.red }} />
                      </td>
                      <td style={{ padding: "3px 6px" }}>
                        <input value={ev.desc} onChange={(e) => updateEvento(ev.id, "desc", e.target.value)}
                          style={{ width: "100%", minWidth: 160, background: C.card2, border: `1px solid ${C.border}`, borderRadius: 5, color: C.text, padding: "3px 6px", fontSize: 11.5 }} />
                      </td>
                      <td style={{ padding: "3px 6px", textAlign: "center" }}>
                        <button onClick={() => removeEvento(ev.id)} title="Eliminar"
                          style={{ background: "none", border: `1px solid ${C.border}`, borderRadius: 5, color: C.red, cursor: "pointer", padding: "2px 8px", fontSize: 12 }}>×</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
              <button onClick={addEvento} style={{
                background: "none", border: `1px solid ${C.border}`, borderRadius: 6,
                color: C.turqSoft, padding: "6px 14px", cursor: "pointer", fontSize: 12,
              }}>+ Agregar evento</button>
              <div style={{ fontSize: 12 }}>
                Neto de eventos: <b style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                  color: eventosExtra.reduce((s,e)=>s+(Number(e.monto)||0),0)>=0?C.greenSoft:C.red }}>
                  {fmtM(eventosExtra.reduce((s,e)=>s+(Number(e.monto)||0),0))}
                </b>
              </div>
            </div>
          </div>

          {/* Pista de caja */}
          <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: 14 }}>
            <div style={{ fontSize: 11, color: C.dim, letterSpacing: ".07em", textTransform: "uppercase", marginBottom: 8 }}>
              Pista de caja · un bloque por mes
            </div>

            <div style={{ fontSize: 10.5, color: C.turqSoft, marginBottom: 4 }}>
              🔮 Proyección (se mueve con tus cambios: supuestos, eventos, deuda y celdas editadas)
            </div>
            <div style={{ display: "flex", gap: 2, flexWrap: "wrap", marginBottom: 12 }}>
              {r.rows.map((x, i) => (
                <div key={i} title={`${x.mes} · caja ${fmtM(x.caja)} · ${x.estado}`} style={{
                  width: 13, height: 26, borderRadius: 3,
                  background: x.estado === "NEGATIVO" ? C.red : x.estado === "CRÍTICO" ? C.amber : C.green,
                  opacity: x.estado === "OK" ? 0.85 : 1, cursor: "default",
                }} />
              ))}
            </div>

            <div style={{ fontSize: 10.5, color: C.dim, marginBottom: 4 }}>
              📊 Excel validado (referencia fija, MAY-26 → DIC-30)
            </div>
            <div style={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
              {cajaExcelData.map((x, i) => {
                const estado = x.caja < 0 ? "NEGATIVO" : x.caja < p.cajaMinima ? "CRÍTICO" : "OK";
                return (
                  <div key={i} title={`${x.mes} · caja ${fmtM(x.caja)} · ${estado}`} style={{
                    width: 13, height: 26, borderRadius: 3,
                    background: estado === "NEGATIVO" ? C.red : estado === "CRÍTICO" ? C.amber : C.green,
                    opacity: estado === "OK" ? 0.6 : 0.8, cursor: "default",
                  }} />
                );
              })}
            </div>

            <div style={{ display: "flex", gap: 14, marginTop: 8, fontSize: 10.5, color: C.dim }}>
              <span><span style={{ color: C.green }}>■</span> OK</span>
              <span><span style={{ color: C.amber }}>■</span> Crítico (bajo caja mínima)</span>
              <span><span style={{ color: C.red }}>■</span> Caja negativa</span>
            </div>
          </div>

          {/* Caja + flujo */}
          <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: "14px 8px 6px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline",
                          flexWrap: "wrap", gap: 6, margin: "0 0 6px 8px" }}>
              <div style={{ fontSize: 11, color: C.dim, letterSpacing: ".07em", textTransform: "uppercase" }}>
                Caja acumulada y flujo neto mensual (millones COP)
              </div>
              <div style={{ fontSize: 10.5, color: C.dim }}>
                Caja mínima Excel: <b style={{ color: C.turqSoft }}>{fmtM(cajaMinExcel.caja)}</b> en {cajaMinExcel.mes}
              </div>
            </div>
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={chartData} margin={{ top: 5, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={C.border} strokeDasharray="2 4" />
                <XAxis dataKey="mes" tick={{ fill: C.dim, fontSize: 9.5 }} interval={Math.max(5, Math.floor(r.rows.length / 12))} />
                <YAxis tick={{ fill: C.dim, fontSize: 10 }} width={58}
                       tickFormatter={(v)=>v>=1000?`${(v/1000).toFixed(1)}mM`:`${v}M`} />
                <Tooltip
                  contentStyle={{ background: C.card2, border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: C.text }}
                  formatter={(v, n) => [n === "Cartera" ? v : fmtM(v * 1e6), n]}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <ReferenceLine y={p.cajaMinima/1e6} stroke={C.amber} strokeDasharray="5 4"
                               label={{ value: "caja mínima", fill: C.amber, fontSize: 10, position: "insideTopRight" }} />
                <ReferenceLine y={0} stroke={C.red} strokeOpacity={0.5} />
                <Bar dataKey="Flujo" fill={C.turq} opacity={0.55} radius={[2,2,0,0]} />
                <Area name="Caja Excel (validado)" dataKey="Caja Excel" type="monotone" stroke={C.greenSoft} strokeWidth={2}
                      fill={C.green} fillOpacity={0.16} />
                <Line name="Caja (proyección — se mueve con tus cambios)" dataKey="Caja" type="monotone" stroke={C.turqSoft} strokeWidth={2.5}
                      strokeDasharray="6 3" dot={false} />
                {escenarios.map((e, i) => (
                  <Line key={e.id} dataKey={`💾 ${e.nombre}`} type="monotone" stroke={COLORES_ESC[i % COLORES_ESC.length]}
                        strokeWidth={1.8} dot={false} />
                ))}
              </ComposedChart>
            </ResponsiveContainer>

            {/* Comparador de escenarios */}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center",
                          margin: "8px 8px 4px", padding: "8px 10px", background: C.card2, borderRadius: 8 }}>
              <span style={{ fontSize: 11, color: C.dim, letterSpacing: ".05em" }}>💾 ESCENARIOS:</span>
              <input value={nombreEscenario} onChange={(e) => setNombreEscenario(e.target.value)}
                placeholder={`Escenario ${escenarios.length + 1} (ej: mora 8%)`}
                style={{ width: 180, background: C.card, border: `1px solid ${C.border}`, borderRadius: 5,
                         color: C.text, padding: "4px 8px", fontSize: 11.5 }} />
              <button onClick={guardarEscenario} disabled={escenarios.length >= 4} style={{
                background: escenarios.length >= 4 ? C.card : C.turq, border: "none", borderRadius: 6,
                color: escenarios.length >= 4 ? C.dim : "#04211f", padding: "5px 12px",
                cursor: escenarios.length >= 4 ? "default" : "pointer", fontSize: 11.5, fontWeight: 700,
              }}>Guardar proyección actual</button>
              {escenarios.map((e, i) => (
                <span key={e.id} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11.5,
                                          border: `1px solid ${COLORES_ESC[i % COLORES_ESC.length]}66`, borderRadius: 14, padding: "3px 10px" }}>
                  <span style={{ width: 9, height: 9, borderRadius: "50%", background: COLORES_ESC[i % COLORES_ESC.length] }} />
                  {e.nombre}
                  <button onClick={() => eliminarEscenario(e.id)} title="Eliminar escenario"
                    style={{ background: "none", border: "none", color: C.red, cursor: "pointer", fontSize: 12, padding: 0 }}>×</button>
                </span>
              ))}
              {escenarios.length === 0 && (
                <span style={{ fontSize: 10.5, color: C.dim }}>
                  Ajusta supuestos y guarda hasta 4 escenarios para compararlos en la gráfica (base / pesimista / optimista).
                </span>
              )}
            </div>
            <div style={{ fontSize: 10.5, color: C.dim, margin: "6px 8px 8px", lineHeight: 1.5 }}>
              El área verde es la caja <b>exacta</b> del archivo Excel validado (MODELO_SIMULADOR_2030_CORREGIDO.xlsm). La línea gris punteada es el simulador del dashboard, que ahora replica la lógica de la macro y del FLUJO DE CAJA (cohortes por miércoles, cartera real previa, pago de lotes Auteco con saldo rodante): en el escenario base ambas líneas se superponen (diferencia &lt; 0,1%). Al mover los controles de la izquierda, la línea gris muestra el nuevo escenario mientras el área verde permanece como referencia validada.
            </div>
          </div>

          {/* Tabla de caja editable (estilo FLUJO DE CAJA del Excel) */}
          <div style={{ background: C.card, border: `1px solid ${C.turq}55`, borderRadius: 12, padding: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, marginBottom: 6 }}>
              <div style={{ fontSize: 11, color: C.dim, letterSpacing: ".07em", textTransform: "uppercase" }}>
                Tabla de caja (editable) · como la hoja FLUJO DE CAJA
              </div>
              {hayOverrides && (
                <button onClick={() => setOverridesMes({})} style={{
                  background: "none", border: `1px solid ${C.amber}`, borderRadius: 6, color: C.amber,
                  padding: "4px 12px", cursor: "pointer", fontSize: 11.5,
                }}>Restablecer valores calculados ({Object.keys(overridesMes).length} mes{Object.keys(overridesMes).length === 1 ? "" : "es"} editado{Object.keys(overridesMes).length === 1 ? "" : "s"})</button>
              )}
            </div>
            <div style={{ fontSize: 11, color: C.dim, marginBottom: 10, lineHeight: 1.5 }}>
              <span style={{ color: C.turqSoft }}>■ Turquesa = editable</span> (Gastos fijos y Pago inventario Auteco) · <span style={{ color: C.text }}>■ Blanco = fórmula</span> (Flujo neto y Caja acumulada se recalculan en cadena hacia el futuro, como el Excel). Edita una celda y toda la caja desde ese mes se actualiza; el pago de inventario editado también propaga su saldo rodante a los meses siguientes. Borra el contenido de una celda para volver al valor calculado. Las celdas editadas quedan marcadas en ámbar.
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ borderCollapse: "collapse", fontSize: 11, whiteSpace: "nowrap",
                              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>
                <thead>
                  <tr style={{ color: C.dim }}>
                    <th style={{ padding: "4px 10px", borderBottom: `1px solid ${C.border}`, textAlign: "left",
                                 position: "sticky", left: 0, background: C.card, zIndex: 1 }}>CONCEPTO</th>
                    {r.rows.map((x) => (
                      <th key={x.mes} style={{ padding: "4px 8px", borderBottom: `1px solid ${C.border}`, textAlign: "right" }}>{x.mes}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td style={{ padding: "3px 10px", color: C.turqSoft, position: "sticky", left: 0, background: C.card, zIndex: 1 }}>Gastos fijos (-)</td>
                    {r.rows.map((x) => {
                      const ov = overridesMes[x.mes]?.gastosFijos;
                      return (
                        <td key={x.mes} style={{ padding: "2px 4px", textAlign: "right" }}>
                          <MontoInput
                            value={ov ?? x.gastosFijos} allowEmpty width={104}
                            onChange={(v) => setOverride(x.mes, "gastosFijos", v)}
                            style={ov != null ? { borderColor: C.amber, color: C.amber } : {}}
                          />
                        </td>
                      );
                    })}
                  </tr>
                  <tr>
                    <td style={{ padding: "3px 10px", color: C.turqSoft, position: "sticky", left: 0, background: C.card, zIndex: 1 }}>Pago inventario Auteco (-)</td>
                    {r.rows.map((x) => {
                      const ov = overridesMes[x.mes]?.pagoInv;
                      return (
                        <td key={x.mes} style={{ padding: "2px 4px", textAlign: "right" }}>
                          <MontoInput
                            value={ov ?? Math.round(x.pagoInv)} allowEmpty width={104}
                            onChange={(v) => setOverride(x.mes, "pagoInv", v)}
                            style={ov != null ? { borderColor: C.amber, color: C.amber } : {}}
                          />
                        </td>
                      );
                    })}
                  </tr>
                  <tr>
                    <td style={{ padding: "3px 10px", color: C.dim, position: "sticky", left: 0, background: C.card, zIndex: 1 }}>Eventos + deuda inversionistas (±)</td>
                    {r.rows.map((x) => {
                      const v = x.extra + x.inyeccion;
                      return (
                        <td key={x.mes} style={{ padding: "3px 8px", textAlign: "right",
                                                 color: v === 0 ? C.dim : v > 0 ? C.greenSoft : C.red }}>{v === 0 ? "—" : fmtInt(v)}</td>
                      );
                    })}
                  </tr>
                  <tr>
                    <td style={{ padding: "3px 10px", color: C.dim, position: "sticky", left: 0, background: C.card, zIndex: 1 }}>Flujo neto mensual (incl. eventos)</td>
                    {r.rows.map((x) => (
                      <td key={x.mes} style={{ padding: "3px 8px", textAlign: "right",
                                               color: x.flujoTotal >= 0 ? C.greenSoft : C.red }}>{fmtInt(x.flujoTotal)}</td>
                    ))}
                  </tr>
                  <tr>
                    <td style={{ padding: "3px 10px", fontWeight: 700, position: "sticky", left: 0, background: C.card, zIndex: 1 }}>Caja acumulada</td>
                    {r.rows.map((x) => (
                      <td key={x.mes} style={{ padding: "3px 8px", textAlign: "right", fontWeight: 700,
                                               color: x.caja < 0 ? C.red : x.caja < p.cajaMinima ? C.amber : C.greenSoft }}>{fmtInt(x.caja)}</td>
                    ))}
                  </tr>
                  <tr>
                    <td style={{ padding: "3px 10px", color: C.dim, fontSize: 10, position: "sticky", left: 0, background: C.card, zIndex: 1 }}>Caja Excel (referencia)</td>
                    {r.rows.map((x) => {
                      const e = cajaExcelPorMes[x.mes];
                      return (
                        <td key={x.mes} style={{ padding: "3px 8px", textAlign: "right", fontSize: 10, color: C.dim }}>{e ? fmtInt(e.caja) : "—"}</td>
                      );
                    })}
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* ── Crédito USD en evaluación + indicadores de crédito ── */}
          <div style={{ background: C.card, border: `1px solid ${C.turq}55`, borderRadius: 12, padding: 14 }}>
            <div style={{ fontSize: 11, color: C.dim, letterSpacing: ".07em", textTransform: "uppercase", marginBottom: 8 }}>
              🏦 Crédito USD en evaluación + indicadores de crédito
            </div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 10 }}>
              <label style={{ fontSize: 10.5, color: C.dim }}>Monto (USD)<br />
                <MontoInput value={creditoUSD.montoUSD} onChange={setCred("montoUSD")} width={110} />
              </label>
              <label style={{ fontSize: 10.5, color: C.dim }}>TRM (COP/USD)<br />
                <MontoInput value={creditoUSD.trm} onChange={setCred("trm")} width={80} />
              </label>
              <label style={{ fontSize: 10.5, color: C.dim }}>Tasa EA %<br />
                <input type="number" step={0.5} value={+(creditoUSD.tasaEA * 100).toFixed(2)}
                  onChange={(e) => setCred("tasaEA")((parseFloat(e.target.value) || 0) / 100)}
                  style={{ width: 68, background: C.card2, border: `1px solid ${C.border}`, borderRadius: 5, color: C.text, padding: "3px 6px", fontSize: 11.5, textAlign: "right" }} />
              </label>
              <label style={{ fontSize: 10.5, color: C.dim }}>Plazo (meses)<br />
                <input type="number" step={12} value={creditoUSD.plazoMeses}
                  onChange={(e) => setCred("plazoMeses")(parseInt(e.target.value) || 1)}
                  style={{ width: 64, background: C.card2, border: `1px solid ${C.border}`, borderRadius: 5, color: C.text, padding: "3px 6px", fontSize: 11.5, textAlign: "right" }} />
              </label>
              <label style={{ fontSize: 10.5, color: C.dim }}>Tipo<br />
                <select value={creditoUSD.tipo} onChange={(e) => setCred("tipo")(e.target.value)}
                  style={{ background: C.card2, border: `1px solid ${C.border}`, borderRadius: 5, color: C.text, padding: "4px 6px", fontSize: 11 }}>
                  <option value="FRANCES">Francés (cuota fija)</option>
                  <option value="BULLET_MENSUAL">Bullet (interés/mes)</option>
                </select>
              </label>
              <label style={{ fontSize: 10.5, color: C.dim }}>Desembolso<br />
                <input type="date" value={creditoUSD.desembolso} onChange={(e) => setCred("desembolso")(e.target.value)}
                  style={{ background: C.card2, border: `1px solid ${C.border}`, borderRadius: 5, color: C.text, padding: "3px 6px", fontSize: 11 }} />
              </label>
              <label style={{ fontSize: 11.5, color: creditoUSD.incluir ? C.greenSoft : C.dim, display: "flex", alignItems: "center", gap: 6, paddingBottom: 4, cursor: "pointer" }}>
                <input type="checkbox" checked={creditoUSD.incluir} onChange={(e) => setCred("incluir")(e.target.checked)}
                  style={{ accentColor: C.turq, width: 15, height: 15, cursor: "pointer" }} />
                Incluir en la proyección
              </label>
            </div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
              <KPI label="Monto en COP" value={fmtM(creditoCalc.montoCOP)} sub={`USD ${Number(creditoUSD.montoUSD).toLocaleString("es-CO")} × TRM ${fmtInt(creditoUSD.trm)}`} />
              <KPI label="Cuota mensual" value={creditoCalc.cuotaBase > 0 ? fmtM(creditoCalc.cuotaBase) : "—"}
                   sub={`US$ ${Math.round(creditoCalc.cuotaBase / (Number(creditoUSD.trm) || 1)).toLocaleString("es-CO")}/mes`} />
              <KPI label="Total intereses" value={fmtM(creditoCalc.totInteres)} sub={`total pagado: ${fmtM(creditoCalc.totPagado)}`} tone="warn" />
              <KPI label="Estado" value={creditoUSD.incluir ? "EN PROYECCIÓN" : "SIN INCLUIR"}
                   sub={creditoUSD.incluir ? "desembolso y pagos afectan la caja e indicadores" : "marca la casilla para simular el impacto"}
                   tone={creditoUSD.incluir ? "good" : undefined} />
            </div>

            <div style={{ fontSize: 11, color: C.dim, letterSpacing: ".07em", textTransform: "uppercase", margin: "4px 0 6px" }}>
              Indicadores de crédito por año {creditoUSD.incluir ? "(incluye el crédito USD)" : "(sin el crédito USD)"}
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ borderCollapse: "collapse", fontSize: 11.5, width: "100%", minWidth: 640,
                              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>
                <thead>
                  <tr style={{ color: C.dim, fontFamily: "inherit" }}>
                    {["Año","Flujo neto anual","Servicio de deuda","DSCR","Deuda / Cartera","Caja mínima del año"].map((h,i)=>(
                      <th key={h} style={{ padding: "4px 8px", borderBottom: `1px solid ${C.border}`, textAlign: i===0?"left":"right", whiteSpace: "nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {indicadoresAnio.map((y) => (
                    <tr key={y.anio}>
                      <td style={{ padding: "3px 8px" }}>{y.anio}</td>
                      <td style={{ padding: "3px 8px", textAlign: "right", color: y.flujoA >= 0 ? C.greenSoft : C.red }}>{fmtInt(y.flujoA)}</td>
                      <td style={{ padding: "3px 8px", textAlign: "right", color: C.dim }}>{fmtInt(y.servicio)}</td>
                      <td style={{ padding: "3px 8px", textAlign: "right", fontWeight: 700,
                                   color: y.dscr == null ? C.dim : y.dscr >= 1.3 ? C.greenSoft : y.dscr >= 1.0 ? C.amber : C.red }}>
                        {y.dscr == null ? "—" : `${y.dscr.toFixed(2)}× ${y.dscr >= 1.3 ? "●" : y.dscr >= 1.0 ? "●" : "●"}`}
                      </td>
                      <td style={{ padding: "3px 8px", textAlign: "right",
                                   color: y.deudaCartera == null ? C.dim : y.deudaCartera <= 0.5 ? C.greenSoft : y.deudaCartera <= 0.8 ? C.amber : C.red }}>
                        {y.deudaCartera == null ? "—" : y.deudaCartera.toFixed(2)}
                      </td>
                      <td style={{ padding: "3px 8px", textAlign: "right",
                                   color: y.cajaMinA < 0 ? C.red : y.cajaMinA < p.cajaMinima ? C.amber : C.greenSoft }}>{fmtInt(y.cajaMinA)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ fontSize: 10.5, color: C.dim, marginTop: 8, lineHeight: 1.5 }}>
              <b>DSCR</b> = (flujo neto anual + servicio de deuda) ÷ servicio de deuda. Servicio = cuota mensual ponderada de la deuda activa × meses del año + pagos únicos al vencimiento del año + pagos del crédito USD (si está incluido). Semáforo: <span style={{ color: C.greenSoft }}>≥ 1,30×</span> · <span style={{ color: C.amber }}>1,00–1,29×</span> · <span style={{ color: C.red }}>&lt; 1,00×</span>. <b>Deuda/Cartera</b> = deuda activa total (+ saldo del crédito USD) ÷ cartera por cobrar al cierre del año — el colateral natural del negocio. Las cuotas de deuda ya están dentro de los gastos/eventos del flujo, por eso el DSCR las suma de vuelta al numerador.
            </div>
          </div>

          {/* ── Sensibilidad y punto de equilibrio ── */}
          <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
              <div style={{ fontSize: 11, color: C.dim, letterSpacing: ".07em", textTransform: "uppercase" }}>
                🎯 Sensibilidad y punto de equilibrio
              </div>
              <button onClick={calcularSensibilidad} disabled={calculandoSens} style={{
                background: C.turq, border: "none", borderRadius: 6, color: "#04211f",
                padding: "6px 14px", cursor: calculandoSens ? "default" : "pointer", fontSize: 12, fontWeight: 700,
                opacity: calculandoSens ? 0.6 : 1,
              }}>{calculandoSens ? "Calculando…" : sensibilidad ? "Recalcular con supuestos actuales" : "Calcular sensibilidad"}</button>
            </div>
            {!sensibilidad ? (
              <div style={{ fontSize: 11.5, color: C.dim, lineHeight: 1.5 }}>
                Corre ~20 simulaciones variando cada supuesto clave para mostrar cuál pega más duro en la caja mínima, y busca el punto de equilibrio: las motos/mes mínimas para que la caja nunca sea negativa en todo el horizonte.
              </div>
            ) : (
              <>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
                  <KPI label="Caja mínima (escenario actual)" value={fmtM(sensibilidad.baseMin)}
                       tone={sensibilidad.baseMin < 0 ? "bad" : sensibilidad.baseMin < p.cajaMinima ? "warn" : "good"} />
                  <KPI label="Punto de equilibrio" value={sensibilidad.equilibrio == null ? "no alcanzable" : `${sensibilidad.equilibrio} motos/mes`}
                       sub={sensibilidad.equilibrio == null ? "ni ×5 las ventas evita caja negativa" : `mínimo para caja nunca negativa · hoy: ${sensibilidad.motosBase}`}
                       tone={sensibilidad.equilibrio == null ? "bad" : sensibilidad.equilibrio <= sensibilidad.motosBase ? "good" : "warn"} />
                </div>
                <div style={{ fontSize: 10.5, color: C.dim, marginBottom: 6 }}>
                  Impacto en la caja mínima al variar cada supuesto (verde = variación favorable, rojo = desfavorable):
                </div>
                {(() => {
                  const maxAbs = Math.max(1, ...sensibilidad.res.flatMap((v) => [Math.abs(v.up), Math.abs(v.dn)]));
                  return sensibilidad.res.map((v) => (
                    <div key={v.key} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                      <div style={{ width: 150, fontSize: 11, color: C.text, textAlign: "right" }}>
                        {v.label} <span style={{ color: C.dim }}>±{Math.round(v.delta * 100)}%</span>
                      </div>
                      <div style={{ flex: 1, display: "flex", height: 16 }}>
                        <div style={{ flex: 1, display: "flex", justifyContent: "flex-end" }}>
                          <div title={`-${Math.round(v.delta*100)}%: ${fmtM(v.dn)}`} style={{
                            width: `${Math.abs(v.dn) / maxAbs * 100}%`, background: v.dn >= 0 ? C.green : C.red,
                            opacity: 0.8, borderRadius: "3px 0 0 3px" }} />
                        </div>
                        <div style={{ width: 1, background: C.dim }} />
                        <div style={{ flex: 1 }}>
                          <div title={`+${Math.round(v.delta*100)}%: ${fmtM(v.up)}`} style={{
                            width: `${Math.abs(v.up) / maxAbs * 100}%`, background: v.up >= 0 ? C.green : C.red,
                            opacity: 0.8, borderRadius: "0 3px 3px 0", height: "100%" }} />
                        </div>
                      </div>
                      <div style={{ width: 170, fontSize: 10, color: C.dim, fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>
                        {fmtM(v.dn)} / {fmtM(v.up)}
                      </div>
                    </div>
                  ));
                })()}
                <div style={{ fontSize: 10.5, color: C.dim, marginTop: 8, lineHeight: 1.5 }}>
                  Cada barra muestra cuánto cambia la caja mínima del horizonte al mover ese supuesto hacia abajo (izquierda) o hacia arriba (derecha), manteniendo todo lo demás igual. Las cifras son Δ caja mínima (−{""}variación / +variación). Si cambias supuestos, eventos o el crédito USD, presiona "Recalcular".
                </div>
              </>
            )}
          </div>

          {/* ── P&G anual ── */}
          <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
              <div style={{ fontSize: 11, color: C.dim, letterSpacing: ".07em", textTransform: "uppercase" }}>
                📑 Estado de resultados anual (P&G devengado)
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <button onClick={() => setMostrarUSD(!mostrarUSD)} style={{
                  background: "none", border: `1px solid ${C.turq}`, borderRadius: 6, color: C.turqSoft,
                  padding: "5px 12px", cursor: "pointer", fontSize: 11.5,
                }}>{mostrarUSD ? `Ver en COP` : `Ver en USD (TRM ${fmtInt(creditoUSD.trm)})`}</button>
                <button onClick={exportarExcel} style={{
                  background: C.turq, border: "none", borderRadius: 6, color: "#04211f",
                  padding: "5px 12px", cursor: "pointer", fontSize: 11.5, fontWeight: 700,
                }}>📤 Exportar a Excel</button>
              </div>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ borderCollapse: "collapse", fontSize: 11.5, width: "100%", minWidth: 720,
                              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>
                <thead>
                  <tr style={{ color: C.dim, fontFamily: "inherit" }}>
                    {["Concepto", ...pygAnual.map((y) => `${y.anio}${y.meses < 12 ? ` (${y.meses}m)` : ""}`)].map((h,i)=>(
                      <th key={h} style={{ padding: "4px 10px", borderBottom: `1px solid ${C.border}`, textAlign: i===0?"left":"right", whiteSpace: "nowrap",
                                           position: i===0?"sticky":"static", left: 0, background: C.card }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[
                    { label: "Ingresos netos", f: (y) => y.ingresos, pos: true },
                    { label: "Costo lotes (motos)", f: (y) => y.costoLotes },
                    { label: "Gastos fijos", f: (y) => y.gastos },
                    { label: "GPS", f: (y) => y.gps },
                    { label: "Financiero (int. + fondeo)", f: (y) => y.financiero },
                  ].map((row) => (
                    <tr key={row.label}>
                      <td style={{ padding: "3px 10px", color: C.dim, fontFamily: "system-ui, sans-serif", position: "sticky", left: 0, background: C.card }}>{row.label}</td>
                      {pygAnual.map((y) => {
                        const v = row.f(y);
                        return <td key={y.anio} style={{ padding: "3px 10px", textAlign: "right", color: v >= 0 ? C.text : C.red }}>{fmtMoneda(v)}</td>;
                      })}
                    </tr>
                  ))}
                  <tr style={{ borderTop: `1px solid ${C.border}` }}>
                    <td style={{ padding: "5px 10px", fontWeight: 800, fontFamily: "system-ui, sans-serif", position: "sticky", left: 0, background: C.card }}>UTILIDAD</td>
                    {pygAnual.map((y) => (
                      <td key={y.anio} style={{ padding: "5px 10px", textAlign: "right", fontWeight: 800,
                                                color: y.utilidad >= 0 ? C.greenSoft : C.red }}>{fmtMoneda(y.utilidad)}</td>
                    ))}
                  </tr>
                  <tr>
                    <td style={{ padding: "3px 10px", color: C.dim, fontFamily: "system-ui, sans-serif", position: "sticky", left: 0, background: C.card }}>Margen neto</td>
                    {pygAnual.map((y) => (
                      <td key={y.anio} style={{ padding: "3px 10px", textAlign: "right",
                                                color: y.margen == null ? C.dim : y.margen >= 0 ? C.turqSoft : C.red }}>{y.margen == null ? "—" : fmtPct(y.margen)}</td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
            <div style={{ fontSize: 10.5, color: C.dim, marginTop: 8, lineHeight: 1.5 }}>
              P&G gerencial devengado: el costo del lote se reconoce en el mes de venta. La exportación genera <b>RODDOS_Proyeccion.xlsx</b> con tres hojas: flujo de caja mensual completo, P&G anual e indicadores de crédito — listo para enviar a un analista. El toggle USD usa la TRM del módulo de crédito de arriba.
            </div>
          </div>

          {/* Márgenes mensuales */}
          <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: "14px 8px 6px" }}>
            <div style={{ fontSize: 11, color: C.dim, letterSpacing: ".07em", textTransform: "uppercase", margin: "0 0 6px 8px" }}>
              Márgenes mes a mes · bruto (sin GPS) y neto (%)
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <ComposedChart data={chartData} margin={{ top: 5, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={C.border} strokeDasharray="2 4" />
                <XAxis dataKey="mes" tick={{ fill: C.dim, fontSize: 9.5 }} interval={Math.max(5, Math.floor(r.rows.length / 12))} />
                <YAxis tick={{ fill: C.dim, fontSize: 10 }} width={44} tickFormatter={(v)=>`${v}%`} />
                <Tooltip
                  contentStyle={{ background: C.card2, border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: C.text }}
                  formatter={(v) => [`${v}%`]}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <ReferenceLine y={0} stroke={C.red} strokeOpacity={0.5} />
                <Line dataKey="M. Bruto %" type="monotone" stroke={C.greenSoft} strokeWidth={2} dot={false} />
                <Line dataKey="M. Neto %" type="monotone" stroke={C.turqSoft} strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
            <div style={{ fontSize: 10.5, color: C.dim, margin: "6px 8px 8px", lineHeight: 1.5 }}>
              Margen bruto = ingreso bruto del mes − costo Auteco de las motos vendidas ese mes (el GPS no entra al margen bruto). Margen neto = utilidad devengada / ingreso neto. Ambos arrancan negativos mientras la cartera madura y se estabilizan al llegar al estado estacionario (~mes {Math.round(p.plazoSemanas/4.33)}).
            </div>
          </div>

          {/* Indicadores por año */}
          <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: 14 }}>
            <div style={{ fontSize: 11, color: C.dim, letterSpacing: ".07em", textTransform: "uppercase", marginBottom: 8 }}>
              Rentabilidad por año · P&G devengado y balance aproximado
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ borderCollapse: "collapse", fontSize: 11.5, width: "100%",
                              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>
                <thead>
                  <tr style={{ color: C.dim }}>
                    {["Año","Utilidad neta","Activos prom.","Patrimonio prom.","ROE","ROA","Margen neto"].map((h,i)=>(
                      <th key={h} style={{ padding: "4px 10px", borderBottom: `1px solid ${C.border}`,
                                           textAlign: i===0?"left":"right", whiteSpace: "nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {r.porAnio.map((a)=>(
                    <tr key={a.anio}>
                      <td style={{ padding: "4px 10px", color: C.dim }}>{a.anio}{a.n<12?` (${a.n}m)`:""}</td>
                      <td style={{ padding: "4px 10px", textAlign: "right",
                                   color: a.utilidad>=0?C.greenSoft:C.red }}>{fmtM(a.utilidad)}</td>
                      <td style={{ padding: "4px 10px", textAlign: "right" }}>{fmtM(a.actProm)}</td>
                      <td style={{ padding: "4px 10px", textAlign: "right",
                                   color: a.patProm>=0?C.text:C.red }}>{fmtM(a.patProm)}</td>
                      <td style={{ padding: "4px 10px", textAlign: "right", fontWeight: 700,
                                   color: (a.roe??0)>=0?C.turqSoft:C.red }}>{fmtPct(a.roe)}</td>
                      <td style={{ padding: "4px 10px", textAlign: "right", fontWeight: 700 }}>{fmtPct(a.roa)}</td>
                      <td style={{ padding: "4px 10px", textAlign: "right" }}>{fmtPct(a.margen)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ fontSize: 10.5, color: C.dim, marginTop: 8, lineHeight: 1.5 }}>
              ROE y ROA usan utilidad anualizada en años parciales. WACD = costo ponderado de la deuda: Auteco efectivo {fmtPct(r.kdAuteco)} EA sobre CxP promedio {fmtM(r.D - p.deuda)} + deuda inversores {fmtPct(r.kdInversores)} EA. WACC = {fmtPct(r.wacc)} con estructura D {fmtM(r.D)} / E {fmtM(r.E)}.
            </div>
          </div>

          {/* Cartera activa */}
          <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: "14px 8px 6px" }}>
            <div style={{ fontSize: 11, color: C.dim, letterSpacing: ".07em", textTransform: "uppercase", margin: "0 0 6px 8px" }}>
              Cartera activa (créditos vigentes) · estado estacionario ≈ motos/mes × {Math.round(p.plazoSemanas/4.33)} meses
            </div>
            <ResponsiveContainer width="100%" height={180}>
              <ComposedChart data={chartData} margin={{ top: 5, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={C.border} strokeDasharray="2 4" />
                <XAxis dataKey="mes" tick={{ fill: C.dim, fontSize: 9.5 }} interval={Math.max(5, Math.floor(r.rows.length / 12))} />
                <YAxis tick={{ fill: C.dim, fontSize: 10 }} width={58} />
                <Tooltip contentStyle={{ background: C.card2, border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 12 }} />
                <Line dataKey="Cartera" type="monotone" stroke={C.turqSoft} strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* Tabla mensual */}
          <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: 14 }}>
            <button onClick={() => setVerTabla(!verTabla)} style={{
              background: "none", border: `1px solid ${C.border}`, borderRadius: 6,
              color: C.turqSoft, padding: "6px 14px", cursor: "pointer", fontSize: 12,
            }}>
              {verTabla ? "Ocultar detalle mensual" : "Ver detalle mensual (flujo + P&G + balance)"}
            </button>
            {verTabla && (
              <div style={{ overflowX: "auto", marginTop: 12 }}>
                <table style={{ borderCollapse: "collapse", fontSize: 11, width: "100%",
                                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>
                  <thead>
                    <tr style={{ color: C.dim, textAlign: "right" }}>
                      {["Mes","Cartera","Recaudo","Ing. neto","M. bruto","MB %","MN %","Flujo","Caja","Utilidad","CxC","CxP Auteco","Patrimonio","Estado"].map((h,i)=>(
                        <th key={h} style={{ padding: "4px 8px", borderBottom: `1px solid ${C.border}`,
                                             textAlign: i===0?"left":"right", whiteSpace: "nowrap" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {r.rows.map((x,i)=>(
                      <tr key={i} style={{ color: C.text }}>
                        <td style={{ padding: "3px 8px", color: C.dim }}>{x.mes}</td>
                        <td style={{ padding: "3px 8px", textAlign: "right" }}>{x.cartera}</td>
                        <td style={{ padding: "3px 8px", textAlign: "right" }}>{fmtM(x.recaudo)}</td>
                        <td style={{ padding: "3px 8px", textAlign: "right" }}>{fmtM(x.neto)}</td>
                        <td style={{ padding: "3px 8px", textAlign: "right",
                                     color: x.margenBruto>=0?C.greenSoft:C.red }}>{fmtM(x.margenBruto)}</td>
                        <td style={{ padding: "3px 8px", textAlign: "right",
                                     color: (x.margenBrutoPct??0)>=0?C.greenSoft:C.red }}>{fmtPct(x.margenBrutoPct,0)}</td>
                        <td style={{ padding: "3px 8px", textAlign: "right",
                                     color: (x.margenNetoPct??0)>=0?C.turqSoft:C.red }}>{fmtPct(x.margenNetoPct,0)}</td>
                        <td style={{ padding: "3px 8px", textAlign: "right",
                                     color: x.flujo>=0?C.greenSoft:C.red }}>{fmtM(x.flujo)}</td>
                        <td style={{ padding: "3px 8px", textAlign: "right", fontWeight: 700,
                                     color: x.caja<0?C.red:x.caja<p.cajaMinima?C.amber:C.greenSoft }}>{fmtM(x.caja)}</td>
                        <td style={{ padding: "3px 8px", textAlign: "right",
                                     color: x.utilidad>=0?C.turqSoft:C.red }}>{fmtM(x.utilidad)}</td>
                        <td style={{ padding: "3px 8px", textAlign: "right" }}>{fmtM(x.cxc)}</td>
                        <td style={{ padding: "3px 8px", textAlign: "right", color: C.amber }}>{fmtM(x.cxpAuteco)}</td>
                        <td style={{ padding: "3px 8px", textAlign: "right",
                                     color: x.patrimonio>=0?C.text:C.red }}>{fmtM(x.patrimonio)}</td>
                        <td style={{ padding: "3px 8px", textAlign: "right", fontSize: 10,
                                     color: x.estado==="OK"?C.green:x.estado==="CRÍTICO"?C.amber:C.red }}>{x.estado}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* ── Ingresos: real vs. proyectado ── */}
          <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: "14px 8px 10px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline",
                          flexWrap: "wrap", gap: 6, margin: "0 0 6px 8px" }}>
              <div style={{ fontSize: 11, color: C.dim, letterSpacing: ".07em", textTransform: "uppercase" }}>
                Ingresos: real vs. proyectado
              </div>
              <div style={{ fontSize: 10.5, color: C.dim }}>
                Real {fmtM(ingresoRealAcum)} · proyectado (mismo período) {fmtM(ingresoProyComparable)}
                {desviacionIngresoPct != null && (
                  <span style={{ color: desviacionIngresoPct >= 0 ? C.greenSoft : C.red, fontWeight: 700 }}> · {fmtPct(desviacionIngresoPct)}</span>
                )}
              </div>
            </div>
            <ResponsiveContainer width="100%" height={200}>
              <ComposedChart data={ingresosChartData} margin={{ top: 5, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={C.border} strokeDasharray="2 4" />
                <XAxis dataKey="mes" tick={{ fill: C.dim, fontSize: 9.5 }} interval={Math.max(5, Math.floor(r.rows.length / 12))} />
                <YAxis tick={{ fill: C.dim, fontSize: 10 }} width={50} tickFormatter={(v) => `${v}M`} />
                <Tooltip
                  contentStyle={{ background: C.card2, border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: C.text }}
                  formatter={(v, n) => [v == null ? "—" : `$${v} M`, n]}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line dataKey="Proyectado" type="monotone" stroke={C.turqSoft} strokeWidth={2} dot={false} />
                <Bar dataKey="Real" fill={C.greenSoft} opacity={0.6} radius={[2,2,0,0]} />
              </ComposedChart>
            </ResponsiveContainer>
            <button onClick={() => setVerIngresos(!verIngresos)} style={{
              background: "none", border: `1px solid ${C.border}`, borderRadius: 6,
              color: C.turqSoft, padding: "6px 14px", cursor: "pointer", fontSize: 12, margin: "8px 0 0 8px",
            }}>
              {verIngresos ? "Ocultar tabla de ingresos" : "Ver / editar ingresos reales mes a mes"}
            </button>
            {verIngresos && (
              <div style={{ overflowX: "auto", marginTop: 10, maxHeight: 260, overflowY: "auto" }}>
                <table style={{ borderCollapse: "collapse", fontSize: 11, width: "100%",
                                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>
                  <thead>
                    <tr style={{ color: C.dim }}>
                      {["Mes","Proyectado","Real (editable)","Variación","Var. %"].map((h,i)=>(
                        <th key={h} style={{ padding: "4px 8px", borderBottom: `1px solid ${C.border}`,
                                             textAlign: i===0?"left":"right", whiteSpace: "nowrap", position: "sticky", top: 0, background: C.card }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {r.rows.map((x, i) => {
                      const real = ingresosReales[i];
                      const varAbs = real == null ? null : real - x.neto;
                      const varPct = real == null || x.neto === 0 ? null : varAbs / x.neto;
                      return (
                        <tr key={i}>
                          <td style={{ padding: "3px 8px", color: C.dim }}>{x.mes}</td>
                          <td style={{ padding: "3px 8px", textAlign: "right" }}>{fmtM(x.neto)}</td>
                          <td style={{ padding: "2px 8px", textAlign: "right" }}>
                            <MontoInput
                              value={real} allowEmpty width={100}
                              onChange={(v) => setIngresosReales((s) => { const n = [...s]; n[i] = v; return n; })}
                            />
                          </td>
                          <td style={{ padding: "3px 8px", textAlign: "right",
                                       color: varAbs == null ? C.dim : varAbs >= 0 ? C.greenSoft : C.red }}>{varAbs == null ? "—" : fmtM(varAbs)}</td>
                          <td style={{ padding: "3px 8px", textAlign: "right",
                                       color: varPct == null ? C.dim : varPct >= 0 ? C.greenSoft : C.red }}>{varPct == null ? "—" : fmtPct(varPct)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <div style={{ fontSize: 10.5, color: C.dim, margin: "8px 0 0 8px" }}>
              Los primeros 6 meses traen cifras de ejemplo — reemplázalas por tus datos reales. Deja el campo vacío para que ese mes solo muestre el proyectado.
            </div>
          </div>

          {/* ── Deuda con inversionistas (real) ── */}
          <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: 14 }}>
            <div style={{ fontSize: 11, color: C.dim, letterSpacing: ".07em", textTransform: "uppercase", marginBottom: 8 }}>
              Deuda con inversionistas (real)
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ borderCollapse: "collapse", fontSize: 11.5, width: "100%", minWidth: 1180 }}>
                <thead>
                  <tr style={{ color: C.dim }}>
                    {["Inversionista","Tipo","Monto","Tasa EA","Tasa mensual","Cuota mensual","Cuota adicional (+)","Pago anual","Desembolso","Vencimiento","Estado","Afecta caja","Flujos",""].map((h,i)=>(
                      <th key={h} style={{ padding: "4px 8px", borderBottom: `1px solid ${C.border}`,
                                           textAlign: i<=1?"left":i>=10?"center":"right", whiteSpace: "nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {inversionistas.map((inv) => {
                    const calc = calcularCredito(inv);
                    return (
                    <tr key={inv.id}>
                      <td style={{ padding: "3px 6px" }}>
                        <input value={inv.nombre} onChange={(e) => updateInversionista(inv.id, "nombre", e.target.value)}
                          style={{ width: 130, background: C.card2, border: `1px solid ${C.border}`, borderRadius: 5, color: C.text, padding: "3px 6px", fontSize: 11.5 }} />
                      </td>
                      <td style={{ padding: "3px 6px" }}>
                        <select value={inv.tipo || "BULLET_MENSUAL"} onChange={(e) => updateInversionista(inv.id, "tipo", e.target.value)}
                          title="Francés: cuota fija (capital+interés). Bullet mensual: solo intereses, capital al final. Bullet vencimiento: todo capitaliza y se paga al final."
                          style={{ background: C.card2, border: `1px solid ${C.border}`, borderRadius: 5, color: C.text, padding: "3px 4px", fontSize: 10.5 }}>
                          <option value="FRANCES">Francés (cuota fija)</option>
                          <option value="BULLET_MENSUAL">Bullet (interés/mes)</option>
                          <option value="BULLET_VENC">Bullet (al vencim.)</option>
                        </select>
                      </td>
                      <td style={{ padding: "3px 6px", textAlign: "right" }}>
                        <MontoInput value={inv.monto} onChange={(n) => updateInversionista(inv.id, "monto", n)} width={100} />
                      </td>
                      <td style={{ padding: "3px 6px", textAlign: "right", whiteSpace: "nowrap" }}>
                        <input type="number" step={0.5} value={+(inv.tasaEA*100).toFixed(2)} onChange={(e) => updateInversionista(inv.id, "tasaEA", (parseFloat(e.target.value) || 0)/100)}
                          style={{ width: 62, background: C.card2, border: `1px solid ${C.border}`, borderRadius: 5, color: C.text, padding: "3px 6px", fontSize: 11.5, textAlign: "right" }} /> %
                      </td>
                      <td style={{ padding: "3px 8px", textAlign: "right", color: C.turqSoft,
                                   fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>
                        {(calc.i * 100).toLocaleString("es-CO", { maximumFractionDigits: 3 })}%
                      </td>
                      <td style={{ padding: "3px 8px", textAlign: "right", color: C.turqSoft,
                                   fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}
                          title={calc.tipo === "BULLET_VENC" ? "Sin cuota mensual: capitaliza y se paga todo al vencimiento" : ""}>
                        {calc.tipo === "BULLET_VENC" ? "— (venc.)" : fmtInt(calc.cuotaBase)}
                      </td>
                      <td style={{ padding: "3px 6px", textAlign: "right" }}>
                        <MontoInput value={inv.cuotaExtra || 0} onChange={(n) => updateInversionista(inv.id, "cuotaExtra", n)} width={90}
                          style={{ color: (inv.cuotaExtra || 0) > 0 ? C.greenSoft : C.dim }} />
                      </td>
                      <td style={{ padding: "3px 8px", textAlign: "right", color: C.dim,
                                   fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}
                          title={calc.tipo === "BULLET_VENC" ? `Pago único al vencimiento: ${fmtInt(calc.totPagado)}` : "Cuota (+ adicional) × 12"}>
                        {calc.tipo === "BULLET_VENC" ? `${fmtInt(calc.totPagado)} (único)` : fmtInt(calc.pagoAnual)}
                      </td>
                      <td style={{ padding: "3px 6px", textAlign: "right" }}>
                        <input type="date" value={inv.desembolso} onChange={(e) => updateInversionista(inv.id, "desembolso", e.target.value)}
                          style={{ background: C.card2, border: `1px solid ${C.border}`, borderRadius: 5, color: C.text, padding: "3px 6px", fontSize: 11 }} />
                      </td>
                      <td style={{ padding: "3px 6px", textAlign: "right" }}>
                        <input type="date" value={inv.vencimiento} onChange={(e) => updateInversionista(inv.id, "vencimiento", e.target.value)}
                          style={{ background: C.card2, border: `1px solid ${C.border}`, borderRadius: 5, color: C.text, padding: "3px 6px", fontSize: 11 }} />
                      </td>
                      <td style={{ padding: "3px 6px", textAlign: "center" }}>
                        <select value={inv.estado} onChange={(e) => updateInversionista(inv.id, "estado", e.target.value)}
                          style={{ background: C.card2, border: `1px solid ${C.border}`, borderRadius: 5, color: C.text, padding: "3px 6px", fontSize: 11 }}>
                          <option value="Activo">Activo</option>
                          <option value="Pagado">Pagado</option>
                        </select>
                      </td>
                      <td style={{ padding: "3px 6px", textAlign: "center" }}>
                        <input type="checkbox" checked={!!inv.afectaCaja}
                          onChange={(e) => updateInversionista(inv.id, "afectaCaja", e.target.checked)}
                          title="Generar desembolso y pagos del cronograma en la proyección de caja"
                          style={{ accentColor: C.turq, cursor: "pointer", width: 15, height: 15 }} />
                      </td>
                      <td style={{ padding: "3px 6px", textAlign: "center" }}>
                        <button onClick={() => setDetalleInvId(inv.id)} title="Ver el cronograma de flujos del crédito"
                          style={{ background: "none", border: `1px solid ${C.turq}`, borderRadius: 5, color: C.turqSoft, cursor: "pointer", padding: "2px 10px", fontSize: 11.5 }}>Ver flujos</button>
                      </td>
                      <td style={{ padding: "3px 6px", textAlign: "center" }}>
                        <button onClick={() => removeInversionista(inv.id)} title="Eliminar"
                          style={{ background: "none", border: `1px solid ${C.border}`, borderRadius: 5, color: C.red, cursor: "pointer", padding: "2px 8px", fontSize: 12 }}>×</button>
                      </td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <button onClick={addInversionista} style={{
              background: "none", border: `1px solid ${C.border}`, borderRadius: 6,
              color: C.turqSoft, padding: "6px 14px", cursor: "pointer", fontSize: 12, marginTop: 10,
            }}>+ Agregar inversionista</button>

            <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center", marginTop: 12,
                          padding: "10px 12px", background: C.card2, borderRadius: 8 }}>
              <div style={{ fontSize: 12 }}>
                Total real: <b style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>{fmtM(totalInversionistas)}</b>
              </div>
              <div style={{ fontSize: 12 }}>
                Cuota mensual ponderada (servicio de deuda): <b style={{ color: C.turqSoft,
                  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>{fmtM(cuotaMensualPonderada)}/mes</b>
              </div>
              <div style={{ fontSize: 12 }}>
                Tasa EA ponderada: <b style={{ color: C.turqSoft }}>{(tasaEAPonderada * 100).toLocaleString("es-CO", { maximumFractionDigits: 2 })}%</b>
              </div>
              {pagoUnicoVencimientos > 0 && (
                <div style={{ fontSize: 12, color: C.dim }}>
                  + pagos únicos al vencimiento: <b style={{ color: C.amber,
                    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>{fmtM(pagoUnicoVencimientos)}</b>
                </div>
              )}
              <div style={{ fontSize: 12, color: C.dim }}>
                Parámetro del modelo (Capital y deuda): <b style={{ color: C.text }}>{fmtM(p.deuda)}</b>
              </div>
              {difiereDelModelo ? (
                <>
                  <span style={{ fontSize: 11.5, color: C.amber }}>⚠ el modelo no coincide con la deuda real cargada</span>
                  <button onClick={() => set("deuda")(totalInversionistas)} style={{
                    background: "none", border: `1px solid ${C.turq}`, borderRadius: 6,
                    color: C.turqSoft, padding: "4px 10px", cursor: "pointer", fontSize: 11.5,
                  }}>Actualizar modelo con este total</button>
                </>
              ) : (
                <span style={{ fontSize: 11.5, color: C.greenSoft }}>✓ el modelo ya refleja este total</span>
              )}
            </div>
            <div style={{ fontSize: 11, color: C.dim, marginTop: 6, lineHeight: 1.5 }}>
              La <b style={{ color: C.turqSoft }}>cuota mensual ponderada</b> suma las cuotas (calculada + adicional) de todas las deudas <i>activas</i> con pago mensual — es el servicio de deuda mensual consolidado de RODDOS. Las notas bullet al vencimiento (Diana, Cesar 1/2) no pagan mensualmente y se muestran aparte como pagos únicos. La <b style={{ color: C.turqSoft }}>tasa EA ponderada</b> pondera la tasa de cada crédito por su monto sobre la deuda activa total.
            </div>
            <div style={{ fontSize: 11, color: C.dim, marginTop: 8, lineHeight: 1.5 }}>
              <b style={{ color: C.turqSoft }}>Cuota mensual</b> se calcula sola según el tipo: <i>Francés</i> = cuota fija (capital + interés), <i>Bullet interés/mes</i> = solo intereses y el capital al vencimiento, <i>Bullet al vencimiento</i> = capitaliza todo y se paga en un único pago final (como las notas convertibles de Diana y los Cesar). <b style={{ color: C.greenSoft }}>Cuota adicional (+)</b>: monto extra que quieras pagar cada mes por encima de la calculada — abona directo a capital y acorta el crédito (en "Ver flujos" ves el efecto). <b style={{ color: C.turqSoft }}>Afecta caja:</b> con la casilla marcada, el crédito inyecta en la proyección el desembolso y cada pago del cronograma. Vienen desmarcadas porque Diana, Cesar 1/2 y Andrés ya están en el flujo base vía eventos, y Fabian (FEC) vía el parámetro "Deuda inversores" — <b style={{ color: C.amber }}>ojo:</b> Raul y David Martinez NO están en el FLUJO DE CAJA del Excel; márcalas si quieres el flujo de deuda completo (y quita el evento correspondiente si marcas una que ya esté ahí, para no duplicar).
            </div>

            <div style={{ fontSize: 11, color: C.dim, letterSpacing: ".07em", textTransform: "uppercase", margin: "14px 0 6px" }}>
              Próximos vencimientos
            </div>
            {proximosVencimientos.length === 0 ? (
              <div style={{ fontSize: 12, color: C.dim }}>Sin vencimientos activos próximos.</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                {proximosVencimientos.map((inv) => (
                  <div key={inv.id} style={{ display: "flex", justifyContent: "space-between", fontSize: 12,
                                              padding: "5px 10px", background: C.card2, borderRadius: 6 }}>
                    <span>{inv.nombre} · {fmtM(inv.monto)}</span>
                    <span style={{ color: inv.dias <= 60 ? C.amber : C.dim }}>
                      {inv.dias < 0 ? `vencido hace ${-inv.dias} d` : `vence en ${inv.dias} d`} · {inv.vencimiento}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ── Detalle de flujos del crédito seleccionado ── */}
          {detalleInvId != null && (() => {
            const inv = inversionistas.find((x) => x.id === detalleInvId);
            if (!inv) return null;
            const calc = calcularCredito(inv);
            const tipoLabel = calc.tipo === "FRANCES" ? "Francés (cuota fija)"
              : calc.tipo === "BULLET_MENSUAL" ? "Bullet (interés mensual, capital al final)"
              : "Bullet (capitaliza, pago único al vencimiento)";
            return (
              <div onClick={() => setDetalleInvId(null)} style={{
                position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", zIndex: 1000,
                display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
              }}>
                <div onClick={(e) => e.stopPropagation()} style={{
                  background: C.card, border: `1px solid ${C.turq}66`, borderRadius: 14,
                  padding: 18, maxWidth: 860, width: "100%", maxHeight: "88vh", overflowY: "auto",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, marginBottom: 4 }}>
                    <div style={{ fontSize: 16, fontWeight: 800 }}>
                      Crédito {inv.nombre} <span style={{ color: C.dim, fontWeight: 400, fontSize: 12 }}>· {tipoLabel}</span>
                    </div>
                    <button onClick={() => setDetalleInvId(null)} style={{
                      background: "none", border: `1px solid ${C.border}`, borderRadius: 6, color: C.text,
                      padding: "5px 14px", cursor: "pointer", fontSize: 12,
                    }}>✕ Volver al dashboard</button>
                  </div>

                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap", margin: "10px 0 14px" }}>
                    <KPI label="Capital" value={fmtM(inv.monto)} sub={`desembolso ${inv.desembolso}`} />
                    <KPI label="Tasa" value={`${(inv.tasaEA * 100).toLocaleString("es-CO", { maximumFractionDigits: 2 })}% EA`}
                         sub={`${(calc.i * 100).toLocaleString("es-CO", { maximumFractionDigits: 3 })}% mensual`} />
                    <KPI label="Cuota mensual" value={calc.tipo === "BULLET_VENC" ? "—" : fmtM(calc.cuotaBase + calc.extra)}
                         sub={calc.extra > 0 ? `incluye +${fmtM(calc.extra)} adicional` : "calculada"} tone={calc.extra > 0 ? "good" : undefined} />
                    <KPI label="Duración real" value={`${calc.mesesReales} meses`}
                         sub={calc.extra > 0 && calc.mesesReales < calc.n ? `${calc.n - calc.mesesReales} meses menos por la cuota adicional` : `plazo pactado: ${calc.n} meses`}
                         tone={calc.extra > 0 && calc.mesesReales < calc.n ? "good" : undefined} />
                    <KPI label="Total intereses" value={fmtM(calc.totInteres)} sub={`total pagado: ${fmtM(calc.totPagado)}`} tone="warn" />
                  </div>

                  <div style={{ overflowX: "auto" }}>
                    <table style={{ borderCollapse: "collapse", fontSize: 11, width: "100%",
                                    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>
                      <thead>
                        <tr style={{ color: C.dim }}>
                          {["#","Mes","Cuota / pago","Interés","Abono capital","Saldo"].map((h,i)=>(
                            <th key={h} style={{ padding: "4px 8px", borderBottom: `1px solid ${C.border}`,
                                                 textAlign: i<=1?"left":"right", whiteSpace: "nowrap",
                                                 position: "sticky", top: 0, background: C.card }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td style={{ padding: "3px 8px", color: C.dim }}>0</td>
                          <td style={{ padding: "3px 8px", color: C.dim }}>{fechaAMesKey(inv.desembolso)}</td>
                          <td style={{ padding: "3px 8px", textAlign: "right", color: C.greenSoft }}>+{fmtInt(inv.monto)}</td>
                          <td style={{ padding: "3px 8px", textAlign: "right", color: C.dim }}>—</td>
                          <td style={{ padding: "3px 8px", textAlign: "right", color: C.dim }}>desembolso</td>
                          <td style={{ padding: "3px 8px", textAlign: "right" }}>{fmtInt(inv.monto)}</td>
                        </tr>
                        {calc.rows.map((row) => (
                          <tr key={row.k} style={{ background: row.pago > 0 ? "transparent" : `${C.card2}88` }}>
                            <td style={{ padding: "3px 8px", color: C.dim }}>{row.k}</td>
                            <td style={{ padding: "3px 8px" }}>{row.key}</td>
                            <td style={{ padding: "3px 8px", textAlign: "right", color: row.pago > 0 ? C.red : C.dim }}>
                              {row.pago > 0 ? `-${fmtInt(row.pago)}` : "capitaliza"}
                            </td>
                            <td style={{ padding: "3px 8px", textAlign: "right", color: C.amber }}>{fmtInt(row.interes)}</td>
                            <td style={{ padding: "3px 8px", textAlign: "right", color: row.abono > 0 ? C.greenSoft : C.dim }}>
                              {row.abono > 0 ? fmtInt(row.abono) : row.pago === 0 ? `+${fmtInt(row.interes)} al saldo` : "0"}
                            </td>
                            <td style={{ padding: "3px 8px", textAlign: "right", fontWeight: row.saldo <= 0.5 ? 700 : 400,
                                         color: row.saldo <= 0.5 ? C.greenSoft : C.text }}>{fmtInt(Math.max(0, row.saldo))}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div style={{ fontSize: 10.5, color: C.dim, marginTop: 10, lineHeight: 1.5 }}>
                    La "Cuota adicional (+)" de la tabla principal se aplica aquí en vivo: abona directo a capital, reduce el interés de los meses siguientes y adelanta la terminación del crédito. Si el crédito tiene "Afecta caja" marcado, estos son exactamente los flujos que entran a la proyección del dashboard.
                  </div>
                </div>
              </div>
            );
          })()}

          {/* ── Presupuesto vs. ejecutado (gastos fijos) ── */}
          <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: "14px 8px 10px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline",
                          flexWrap: "wrap", gap: 6, margin: "0 0 6px 8px" }}>
              <div style={{ fontSize: 11, color: C.dim, letterSpacing: ".07em", textTransform: "uppercase" }}>
                Presupuesto vs. ejecutado (gastos fijos)
              </div>
              <div style={{ fontSize: 10.5, color: C.dim }}>
                Ejecutado {fmtM(gastoRealAcum)} · presupuestado (mismo período) {fmtM(gastoPresupuestadoComparable)}
                {desviacionGastoPct != null && (
                  <span style={{ color: desviacionGastoPct <= 0 ? C.greenSoft : C.red, fontWeight: 700 }}> · {fmtPct(desviacionGastoPct)}</span>
                )}
              </div>
            </div>
            <ResponsiveContainer width="100%" height={200}>
              <ComposedChart data={gastosChartData} margin={{ top: 5, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={C.border} strokeDasharray="2 4" />
                <XAxis dataKey="mes" tick={{ fill: C.dim, fontSize: 9.5 }} interval={Math.max(5, Math.floor(r.rows.length / 12))} />
                <YAxis tick={{ fill: C.dim, fontSize: 10 }} width={50} tickFormatter={(v) => `${v}M`} />
                <Tooltip
                  contentStyle={{ background: C.card2, border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: C.text }}
                  formatter={(v, n) => [v == null ? "—" : `$${v} M`, n]}
                />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line dataKey="Presupuestado" type="monotone" stroke={C.turqSoft} strokeWidth={2} dot={false} />
                <Bar dataKey="Ejecutado" fill={C.amber} opacity={0.55} radius={[2,2,0,0]} />
              </ComposedChart>
            </ResponsiveContainer>
            <button onClick={() => setVerGastos(!verGastos)} style={{
              background: "none", border: `1px solid ${C.border}`, borderRadius: 6,
              color: C.turqSoft, padding: "6px 14px", cursor: "pointer", fontSize: 12, margin: "8px 0 0 8px",
            }}>
              {verGastos ? "Ocultar tabla de ejecución" : "Ver / editar ejecución real mes a mes"}
            </button>
            {verGastos && (
              <div style={{ overflowX: "auto", marginTop: 10, maxHeight: 260, overflowY: "auto" }}>
                <table style={{ borderCollapse: "collapse", fontSize: 11, width: "100%",
                                fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>
                  <thead>
                    <tr style={{ color: C.dim }}>
                      {["Mes","Presupuestado","Ejecutado (editable)","Variación","Var. %"].map((h,i)=>(
                        <th key={h} style={{ padding: "4px 8px", borderBottom: `1px solid ${C.border}`,
                                             textAlign: i===0?"left":"right", whiteSpace: "nowrap", position: "sticky", top: 0, background: C.card }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {r.rows.map((x, i) => {
                      const real = gastosReales[i];
                      const varAbs = real == null ? null : real - p.gastosFijos;
                      const varPct = real == null || p.gastosFijos === 0 ? null : varAbs / p.gastosFijos;
                      return (
                        <tr key={i}>
                          <td style={{ padding: "3px 8px", color: C.dim }}>{x.mes}</td>
                          <td style={{ padding: "3px 8px", textAlign: "right" }}>{fmtM(p.gastosFijos)}</td>
                          <td style={{ padding: "2px 8px", textAlign: "right" }}>
                            <MontoInput
                              value={real} allowEmpty width={100}
                              onChange={(v) => setGastosReales((s) => { const n = [...s]; n[i] = v; return n; })}
                            />
                          </td>
                          <td style={{ padding: "3px 8px", textAlign: "right",
                                       color: varAbs == null ? C.dim : varAbs <= 0 ? C.greenSoft : C.red }}>{varAbs == null ? "—" : fmtM(varAbs)}</td>
                          <td style={{ padding: "3px 8px", textAlign: "right",
                                       color: varPct == null ? C.dim : varPct <= 0 ? C.greenSoft : C.red }}>{varPct == null ? "—" : fmtPct(varPct)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <div style={{ fontSize: 10.5, color: C.dim, margin: "8px 0 0 8px" }}>
              El presupuesto sale del parámetro "Gastos fijos / mes" en el panel de Operación. Los primeros 6 meses traen ejecución de ejemplo — reemplázala por tus cifras reales.
            </div>
          </div>

          <div style={{ fontSize: 10.5, color: C.dim, lineHeight: 1.5 }}>
            Nota metodológica: cohortes semanales (ciclo 5-4-4, 13 sem/trimestre); cada crédito paga {p.plazoSemanas} cuotas desde la venta. Lote Auteco pagado {Math.floor(p.plazoAutecoDias/30)} meses después, neto de adelantos, más {Math.max(0, Math.floor(p.plazoAutecoDias/30)-Math.floor(p.baseAutecoDias/30))} mes(es) de interés al {(p.tasaAuteco*100).toFixed(1)}% sobre valor bruto. <b>P&G devengado</b>: el costo del lote se reconoce en el mes de venta (conservador en fase de crecimiento). <b>Balance aproximado</b>: Activos = caja + cartera por cobrar (cuotas pendientes); Pasivos = deuda inversores + CxP Auteco; Patrimonio residual. <b>Validación (JUL-2026):</b> parámetros, caja inicial (${fmtM(24000000)} reales de MAY-26), rampa de ventas (18→50→60 motos/mes) y horizonte (MAY-26→DIC-30) verificados contra MODELO_SIMULADOR_2030_CORREGIDO.xlsm. La línea "Caja Excel" del gráfico de caja es la cifra exacta del Excel; el área verde es el simulador paramétrico, que coincide con el Excel en el escenario base gracias a los eventos extraordinarios cargados arriba, y se desvía de forma controlada al cambiar los supuestos. Estos indicadores son gerenciales — para Bancóldex u otros usos regulatorios se calculan sobre los EEFF certificados.
          </div>
        </div>
      </div>
    </div>
  );
}
