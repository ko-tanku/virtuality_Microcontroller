import { useMemo, useState } from 'react'
import { Assembler } from './tools/assembler/Assembler'
import { CpuCore } from './core/cpu/CpuCore'
import { Memory } from './core/memory/Memory'
import { MEMORY_MAP } from './core/memory/MemoryMap'

type CpuSnapshot = {
  pc: number
  usp: number
  isp: number
  r: number[]
  psw: {
    I: boolean
    U: boolean
    PM: boolean
    IPL: number
    O: boolean
    S: boolean
    Z: boolean
    C: boolean
  }
}

const defaultSource = `; RX65N minimal demo (subset)
; MOV.L #1, R1
; ADD.L #2, R1
; MOV.L R1, R2
MOV.L #1, R1
ADD.L #2, R1
MOV.L R1, R2
NOP
`

const toHex = (value: number, digits = 8) =>
  '0x' + value.toString(16).toUpperCase().padStart(digits, '0')

const snapshotCpu = (cpu: CpuCore): CpuSnapshot => ({
  pc: cpu.pc >>> 0,
  usp: cpu.usp >>> 0,
  isp: cpu.isp >>> 0,
  r: Array.from(cpu.r).map(v => v >>> 0),
  psw: { ...cpu.psw }
})

function App() {
  const memory = useMemo(() => new Memory(), [])
  const cpu = useMemo(() => new CpuCore(memory), [memory])
  const assembler = useMemo(() => new Assembler(), [])

  const [source, setSource] = useState(defaultSource)
  const [errors, setErrors] = useState<string[]>([])
  const [log, setLog] = useState<string[]>([])
  const [snapshot, setSnapshot] = useState<CpuSnapshot>(() => snapshotCpu(cpu))

  const appendLog = (line: string) =>
    setLog(prev => [...prev, line])

  const assembleAndReset = () => {
    const result = assembler.assemble(source)
    setErrors(result.errors)

    if (result.errors.length > 0) {
      appendLog('Assemble failed: check errors.')
      return
    }

    memory.reset()
    memory.load(result.code, MEMORY_MAP.ROM_START)
    memory.write32(0xFFFFFFFC, MEMORY_MAP.ROM_START)
    cpu.reset()
    setSnapshot(snapshotCpu(cpu))
    appendLog(`Loaded ${result.code.length} bytes @ ${toHex(MEMORY_MAP.ROM_START)}`)
  }

  const doStep = () => {
    const cycles = cpu.step()
    setSnapshot(snapshotCpu(cpu))
    appendLog(`Step: PC=${toHex(cpu.pc)} Cycles=${cycles}`)
  }

  const runSteps = (steps: number) => {
    for (let i = 0; i < steps; i += 1) {
      cpu.step()
    }
    setSnapshot(snapshotCpu(cpu))
    appendLog(`Run ${steps} steps: PC=${toHex(cpu.pc)}`)
  }

  const resetOnly = () => {
    cpu.reset()
    setSnapshot(snapshotCpu(cpu))
    appendLog('CPU reset.')
  }

  return (
    <div className="min-h-screen bg-gray-100 p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        <header className="space-y-1">
          <h1 className="text-3xl font-bold text-gray-800">RX65N Web Simulator</h1>
          <p className="text-gray-600">
            Assembler → ROM → CPU step execution (subset)
          </p>
        </header>

        <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white rounded-lg shadow p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-800">Assembly</h2>
              <span className="text-sm text-gray-500">
                Load @ {toHex(MEMORY_MAP.ROM_START)}
              </span>
            </div>
            <textarea
              className="w-full h-64 font-mono text-sm border rounded p-2 focus:outline-none focus:ring"
              value={source}
              onChange={e => setSource(e.target.value)}
            />
            <div className="flex flex-wrap gap-2">
              <button
                className="px-3 py-2 rounded bg-blue-600 text-white text-sm hover:bg-blue-700"
                onClick={assembleAndReset}
              >
                Assemble & Reset
              </button>
              <button
                className="px-3 py-2 rounded bg-gray-200 text-sm hover:bg-gray-300"
                onClick={resetOnly}
              >
                Reset
              </button>
              <button
                className="px-3 py-2 rounded bg-green-600 text-white text-sm hover:bg-green-700"
                onClick={doStep}
              >
                Step
              </button>
              <button
                className="px-3 py-2 rounded bg-green-600 text-white text-sm hover:bg-green-700"
                onClick={() => runSteps(10)}
              >
                Run 10
              </button>
              <button
                className="px-3 py-2 rounded bg-green-600 text-white text-sm hover:bg-green-700"
                onClick={() => runSteps(100)}
              >
                Run 100
              </button>
            </div>

            {errors.length > 0 && (
              <div className="bg-red-50 border border-red-200 rounded p-2 text-sm text-red-700">
                <p className="font-semibold">Errors</p>
                <ul className="list-disc pl-5">
                  {errors.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <div className="bg-white rounded-lg shadow p-4 space-y-4">
            <h2 className="text-lg font-semibold text-gray-800">CPU State</h2>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="space-y-1">
                <div><span className="font-semibold">PC:</span> {toHex(snapshot.pc)}</div>
                <div><span className="font-semibold">USP:</span> {toHex(snapshot.usp)}</div>
                <div><span className="font-semibold">ISP:</span> {toHex(snapshot.isp)}</div>
              </div>
              <div className="space-y-1">
                <div><span className="font-semibold">PSW:</span></div>
                <div className="grid grid-cols-4 gap-1">
                  {(['I','U','PM','O','S','Z','C'] as const).map(flag => (
                    <span
                      key={flag}
                      className={`px-2 py-1 rounded text-center ${snapshot.psw[flag] ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-500'}`}
                    >
                      {flag}
                    </span>
                  ))}
                  <span className="px-2 py-1 rounded text-center bg-gray-100 text-gray-500">
                    IPL:{snapshot.psw.IPL}
                  </span>
                </div>
              </div>
            </div>

            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-2">Registers</h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
                {snapshot.r.map((val, i) => (
                  <div key={i} className="bg-gray-50 border rounded p-2">
                    <div className="text-gray-500">R{i}</div>
                    <div>{toHex(val)}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="bg-white rounded-lg shadow p-4">
          <h2 className="text-lg font-semibold text-gray-800 mb-2">Log</h2>
          <div className="h-40 overflow-auto bg-gray-50 border rounded p-2 text-xs font-mono">
            {log.length === 0 ? (
              <div className="text-gray-400">No logs yet.</div>
            ) : (
              log.map((line, i) => <div key={i}>{line}</div>)
            )}
          </div>
        </section>
      </div>
    </div>
  )
}

export default App