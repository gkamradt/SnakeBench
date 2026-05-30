import { notFound } from 'next/navigation'
import MatchInfo from '@/components/match/MatchInfo'
import GameViewer, { BoardInfo, NormalizedFrame, MoveEntry } from '@/components/match/GameViewer'

type PlayerEntry = {
  model_id: string
  name: string
  result?: string
  final_score?: number
  death?: { reason?: string; round?: number }
}

type GamePayload = {
  id: string
  started_at?: string
  ended_at?: string
  game_type?: string
  max_rounds?: number
  rounds_played?: number
  board: BoardInfo
}

type ReplayPayload = {
  version: number
  game: GamePayload
  players: Record<string, PlayerEntry>
  frames: NormalizedFrame[]
}

type RawReplay = {
  version?: number
  game?: Partial<GamePayload> & { board?: Partial<BoardInfo> }
  players?: Record<string, PlayerEntry>
  frames?: Array<Partial<NormalizedFrame>>
}

type RawBoard = Partial<BoardInfo>

interface PageProps {
  params: Promise<{ id: string }>
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}

function normalizeReplay(raw: unknown): ReplayPayload {
  if (!raw || typeof raw !== 'object') {
    throw new Error("Replay is missing required fields for the new schema.")
  }

  const data = raw as RawReplay
  if (!data.frames || !data.game || !data.players) {
    throw new Error("Replay is missing required fields for the new schema.")
  }

  const board = (data.game.board || {}) as RawBoard
  const width = board.width
  const height = board.height
  const numApples = board.num_apples
  const gameId = data.game.id

  if (typeof width !== 'number' || typeof height !== 'number') {
    throw new Error("Replay board is missing width/height.")
  }
  if (typeof gameId !== 'string') {
    throw new Error("Replay is missing game id.")
  }

  const frames: NormalizedFrame[] = (data.frames || []).map((frame, idx: number) => ({
    round: typeof frame?.round === 'number' ? frame.round : idx,
    state: {
      snakes: frame?.state?.snakes || {},
      apples: frame?.state?.apples || [],
      alive: frame?.state?.alive || {},
      scores: frame?.state?.scores || {},
    },
    moves: frame?.moves as Record<string, MoveEntry> | undefined,
    events: frame?.events,
  }))

  return {
    version: data.version ?? 1,
    game: {
      id: gameId,
      started_at: data.game.started_at,
      ended_at: data.game.ended_at,
      game_type: data.game.game_type,
      max_rounds: data.game.max_rounds,
      rounds_played: data.game.rounds_played,
      board: {
        width,
        height,
        num_apples: numApples,
      }
    },
    players: data.players,
    frames
  }
}

export default async function MatchPage(props: PageProps) {
  const params = await props.params
  const search = await props.searchParams
  const captureMode = search?.capture === '1' || search?.capture === 'true'
  const { id } = params

  // Fetch replay directly from Supabase Storage
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
  const bucket = 'matches'
  const replayUrl = `${supabaseUrl}/storage/v1/object/public/${bucket}/${id}/replay.json`

  const gamesResponse = await fetch(replayUrl, { next: { revalidate: 300 } }) // revalidate every 5 minutes

  // If not found or error
  if (!gamesResponse.ok) {
    notFound()
  }

  // Parse and normalize the JSON (new schema only)
  const rawReplay = await gamesResponse.json()
  let replay: ReplayPayload
  try {
    replay = normalizeReplay(rawReplay)
  } catch (err) {
    console.error(err)
    notFound()
  }

  const startTime = replay.game.started_at ? new Date(replay.game.started_at) : null
  const formattedDate = startTime
    ? startTime.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
    : 'Unknown date'
  const formattedTime = startTime
    ? startTime.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : 'Unknown time'

  const modelIds = Object.keys(replay.players || {})
  const modelNames = modelIds.map(id => replay.players[id]?.name || `Player ${id}`)

  if (captureMode) {
    // Stripped-down layout for headless video capture: no nav, no footer,
    // no MatchInfo. Driven via window.__capture from Playwright.
    return (
      <>
        {/* Hide global chrome from RootLayout so the capture viewport
            contains only the gameplay UI. */}
        <style>{`
          nav, footer { display: none !important; }
          body { background: #f9fafb !important; }
          main { padding: 0 !important; margin: 0 !important; }
        `}</style>
        <div data-capture-root className="bg-gray-50">
          <div className="max-w-7xl mx-auto p-6">
            <GameViewer
              frames={replay.frames}
              board={replay.game.board}
              modelIds={modelIds}
              modelNames={modelNames}
              gameId={replay.game.id}
              captureMode
            />
          </div>
        </div>
      </>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto py-4 sm:py-6 px-4 sm:px-6 lg:px-8">
        <MatchInfo modelNames={modelNames} date={formattedDate} time={formattedTime} />

        <GameViewer
          frames={replay.frames}
          board={replay.game.board}
          modelIds={modelIds}
          modelNames={modelNames}
          gameId={replay.game.id}
        />
      </div>
    </div>
  )
}
