/**
 * Author: Cascade
 * Date: 2025-12-19
 * PURPOSE: Server Component for the Skill Analysis page. Fetches leaderboard data
 *          and passes it to the client component for interactive visualization.
 * SRP/DRY check: Pass - server-side data fetching only; rendering delegated to client.
 */

import { fetchLeaderboardData, fetchModelRating, computeAxisDomains } from '@/lib/api/trueskill';
import SkillAnalysisClient from './SkillAnalysisClient';

interface PageProps {
  searchParams: Promise<{ model?: string; reference?: string }>;
}

export const metadata = {
  title: 'Skill Analysis | SnakeBench',
  description: 'Explore TrueSkill ratings with interactive bell curve visualizations, confidence intervals, and win probability calculations.',
};

export default async function SkillAnalysisPage({ searchParams }: PageProps) {
  // Await searchParams (Next.js 15 async params)
  const params = await searchParams;

  // Fetch leaderboard data
  const leaderboard = await fetchLeaderboardData(150);

  // Determine selected models from URL params or defaults
  const selectedModelSlug = params.model || leaderboard[0]?.modelSlug || null;
  const referenceModelSlug = params.reference || leaderboard[1]?.modelSlug || null;

  // Fetch individual model ratings in parallel
  const [selectedModel, referenceModel] = await Promise.all([
    selectedModelSlug ? fetchModelRating(selectedModelSlug) : null,
    referenceModelSlug ? fetchModelRating(referenceModelSlug) : null,
  ]);

  // Compute stable axis domains for scatter plot
  const axisDomains = computeAxisDomains(leaderboard);

  return (
    <SkillAnalysisClient
      leaderboard={leaderboard}
      initialSelectedModel={selectedModel}
      initialReferenceModel={referenceModel}
      initialSelectedSlug={selectedModelSlug}
      initialReferenceSlug={referenceModelSlug}
      axisDomains={axisDomains}
    />
  );
}
