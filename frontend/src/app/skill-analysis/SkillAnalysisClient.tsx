/**
 * Author: Cascade
 * Date: 2025-12-19
 * PURPOSE: Client Component for the Skill Analysis page. Handles interactive state,
 *          URL updates, and renders the visualization components.
 * SRP/DRY check: Pass - client-side interactivity only; data fetching done in server component.
 */

"use client"

import React, { useState, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { InlineMath } from 'react-katex';

import { Card } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';
import { TooltipProvider } from '@/components/ui/tooltip';
import { ScrollArea } from '@/components/ui/scroll-area';

import SkillDistributionChart from '@/components/skill-analysis/SkillDistributionChart';
import SkillMetrics from '@/components/skill-analysis/SkillMetrics';
import WinProbability from '@/components/skill-analysis/WinProbability';
import SkillScatterPlot from '@/components/skill-analysis/SkillScatterPlot';
import MultiCurveOverlay from '@/components/skill-analysis/MultiCurveOverlay';

import type { TrueSkillLeaderboardEntry, TrueSkillModelRating } from '@/types/trueskill';
import { MULTI_CURVE_PALETTE } from '@/lib/roleColors';

interface SkillAnalysisClientProps {
  leaderboard: TrueSkillLeaderboardEntry[];
  initialSelectedModel: TrueSkillModelRating | null;
  initialReferenceModel: TrueSkillModelRating | null;
  initialSelectedSlug: string | null;
  initialReferenceSlug: string | null;
  axisDomains: {
    muDomain: { min: number; max: number };
    sigmaDomain: { min: number; max: number };
  };
}

/**
 * Build URL for skill analysis page with model selections.
 */
function buildSkillAnalysisUrl(modelSlug: string | null, referenceSlug: string | null): string {
  const params = new URLSearchParams();
  if (modelSlug) params.set('model', modelSlug);
  if (referenceSlug) params.set('reference', referenceSlug);
  const qs = params.toString();
  return qs ? `/skill-analysis?${qs}` : '/skill-analysis';
}

export default function SkillAnalysisClient({
  leaderboard,
  initialSelectedModel,
  initialReferenceModel,
  initialSelectedSlug,
  initialReferenceSlug,
  axisDomains,
}: SkillAnalysisClientProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  // State for model selections
  const [selectedSlug, setSelectedSlug] = useState(initialSelectedSlug);
  const [referenceSlug, setReferenceSlug] = useState(initialReferenceSlug);
  const [selectedFilter, setSelectedFilter] = useState('');
  const [referenceFilter, setReferenceFilter] = useState('');
  const [viewMode, setViewMode] = useState<'poster' | 'comparison'>('poster');
  const [hoveredModel, setHoveredModel] = useState<string | null>(null);

  // Comparison view selections (up to 5 models)
  const [comparisonSelections, setComparisonSelections] = useState<string[]>(() => {
    const seeds = [initialSelectedSlug, initialReferenceSlug].filter(Boolean) as string[];
    return Array.from(new Set(seeds));
  });

  // Get current model data from leaderboard
  const selectedModel = useMemo(
    () => leaderboard.find((e) => e.modelSlug === selectedSlug) || initialSelectedModel,
    [leaderboard, selectedSlug, initialSelectedModel]
  );

  const referenceModel = useMemo(
    () => leaderboard.find((e) => e.modelSlug === referenceSlug) || initialReferenceModel,
    [leaderboard, referenceSlug, initialReferenceModel]
  );

  // Filter leaderboard for model selectors
  const filteredForSelected = useMemo(() => {
    if (!selectedFilter) return leaderboard;
    const lower = selectedFilter.toLowerCase();
    return leaderboard.filter((e) => e.modelSlug.toLowerCase().includes(lower));
  }, [leaderboard, selectedFilter]);

  const filteredForReference = useMemo(() => {
    if (!referenceFilter) return leaderboard;
    const lower = referenceFilter.toLowerCase();
    return leaderboard.filter((e) => e.modelSlug.toLowerCase().includes(lower));
  }, [leaderboard, referenceFilter]);

  // Get models for comparison overlay
  const comparisonModels = useMemo(
    () => leaderboard.filter((e) => comparisonSelections.includes(e.modelSlug)),
    [leaderboard, comparisonSelections]
  );

  // Handle model selection
  const handleSelectModel = (slug: string) => {
    setSelectedSlug(slug);
    router.push(buildSkillAnalysisUrl(slug, referenceSlug));
  };

  const handleSelectReference = (slug: string) => {
    setReferenceSlug(slug);
    router.push(buildSkillAnalysisUrl(selectedSlug, slug));
  };

  // Handle scatter plot point click (toggle in comparison selections)
  const handleScatterPointClick = (slug: string) => {
    setComparisonSelections((prev) => {
      if (prev.includes(slug)) {
        return prev.filter((s) => s !== slug);
      }
      // Limit to 5 selections
      if (prev.length >= 5) {
        return [...prev.slice(1), slug];
      }
      return [...prev, slug];
    });
  };

  return (
    <TooltipProvider>
      <div className="min-h-screen bg-gray-50">
        <div className="max-w-[1500px] mx-auto px-4 md:px-6 py-6 space-y-6">
          {/* Page header */}
          <div className="text-center">
            <h1 className="text-2xl font-press-start text-gray-900">TrueSkill Analysis</h1>
            <p className="mt-2 text-sm font-mono text-gray-500">
              Explore skill distributions, confidence intervals, and win probabilities
            </p>
          </div>

          {/* TrueSkill Explainer Accordion */}
          <div className="flex justify-center">
            <Card className="w-full max-w-3xl">
              <Accordion type="single" collapsible className="w-full">
                <AccordionItem value="trueskill-explainer" className="border-b-0">
                  <AccordionTrigger className="px-4 py-2 hover:no-underline">
                    <div className="w-full flex justify-center">
                      <span className="text-sm font-semibold text-gray-800">Why TrueSkill?</span>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="px-4 pb-3 pt-1 text-sm text-gray-500 space-y-3">
                    <div>
                      <strong className="text-gray-800">What is TrueSkill?</strong>
                      <p className="mt-1">
                        TrueSkill is a Bayesian skill rating system developed by Microsoft. Unlike simple win/loss ratios, it accounts for
                        opponent strength and adjusts ratings based on match outcomes.
                      </p>
                    </div>

                    <div>
                      <strong className="text-gray-800">Why not just use W/L ratio?</strong>
                      <p className="mt-1">
                        A 70% win rate against weak opponents is less impressive than a 50% win rate against strong opponents. TrueSkill
                        captures this nuance by considering who you play against.
                      </p>
                    </div>

                    <div>
                      <strong className="text-gray-800">
                        What do <InlineMath math="\\mu" /> and <InlineMath math="\\sigma" /> mean?
                      </strong>
                      <p className="mt-1">
                        <InlineMath math="\\mu" /> (mu) is the estimated skill level. <InlineMath math="\\sigma" /> (sigma) is the uncertainty. A small{' '}
                        <InlineMath math="\\sigma" /> means consistent performance across many games. A large{' '}
                        <InlineMath math="\\sigma" /> means the model is new or plays inconsistently.
                      </p>
                    </div>

                    <div>
                      <strong className="text-gray-800">What is the confidence interval?</strong>
                      <p className="mt-1">
                        The 99.7% confidence interval (<InlineMath math="\\mu \\pm 3\\sigma" />) shows the range where your true skill likely
                        falls. The &quot;pessimistic rating&quot; is the lower bound; the &quot;optimistic rating&quot; is the upper bound.
                      </p>
                    </div>

                    <div>
                      <strong className="text-gray-800">How does leaderboard ranking work?</strong>
                      <p className="mt-1">
                        Models are ranked by their &quot;exposed&quot; rating (<InlineMath math="\\mu - 3\\sigma" />), the pessimistic bound. This
                        rewards both consistency and strength, penalizing new models with high uncertainty.
                      </p>
                    </div>

                    <div className="pt-2 border-t border-gray-200">
                      <a
                        href="https://www.microsoft.com/en-us/research/project/trueskill-ranking-system/"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:underline font-semibold"
                      >
                        Learn more about TrueSkill (Microsoft Research)
                      </a>
                    </div>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </Card>
          </div>

          {/* Main 3-column layout */}
          <div className="grid grid-cols-1 xl:grid-cols-[minmax(300px,1fr)_minmax(0,1.8fr)_minmax(300px,1fr)] gap-6 items-start">
            {/* LEFT: Compare model selector */}
            <div className="space-y-4">
              <Card className="p-4">
                <div className="mb-3">
                  <h3 className="text-sm font-bold text-gray-800">Compare Model</h3>
                  <p className="text-xs text-gray-500">Sorted by games played</p>
                </div>
                <input
                  type="text"
                  placeholder="Search models..."
                  value={selectedFilter}
                  onChange={(e) => setSelectedFilter(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-md mb-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <ScrollArea className="h-[280px]">
                  <div className="space-y-1">
                    {filteredForSelected
                      .sort((a, b) => b.gamesPlayed - a.gamesPlayed)
                      .map((entry) => (
                        <button
                          key={entry.modelSlug}
                          onClick={() => handleSelectModel(entry.modelSlug)}
                          className={`w-full text-left px-3 py-2 text-xs rounded-md transition-colors ${
                            entry.modelSlug === selectedSlug
                              ? 'bg-blue-100 text-blue-800 font-semibold'
                              : 'hover:bg-gray-100 text-gray-700'
                          }`}
                        >
                          <div className="font-medium truncate">{entry.modelSlug}</div>
                          <div className="text-gray-500">
                            {entry.gamesPlayed} games - {entry.wins}W/{entry.losses}L
                          </div>
                        </button>
                      ))}
                  </div>
                </ScrollArea>
              </Card>

              {/* Selected model snapshot */}
              {selectedModel && (
                <Card className="p-4">
                  <h4 className="text-sm font-bold text-blue-600 truncate">{selectedModel.modelSlug}</h4>
                  <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-gray-500">mu:</span>{' '}
                      <span className="font-mono font-semibold">{selectedModel.mu.toFixed(2)}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">sigma:</span>{' '}
                      <span className="font-mono font-semibold">{selectedModel.sigma.toFixed(2)}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">exposed:</span>{' '}
                      <span className="font-mono font-semibold">{selectedModel.exposed.toFixed(2)}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">games:</span>{' '}
                      <span className="font-mono font-semibold">{selectedModel.gamesPlayed}</span>
                    </div>
                  </div>
                </Card>
              )}
            </div>

            {/* MIDDLE: Poster/Comparison tabs */}
            <div className="min-w-0">
              <Tabs
                value={viewMode}
                onValueChange={(v) => setViewMode(v as 'poster' | 'comparison')}
                className="w-full"
              >
                <TabsList className="w-full">
                  <TabsTrigger value="poster" className="flex-1">
                    Poster View
                  </TabsTrigger>
                  <TabsTrigger value="comparison" className="flex-1">
                    Comparison View
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="poster" className="mt-4">
                  <Card className="p-6">
                    {selectedModel ? (
                      <div className="space-y-8">
                        {/* Bell curve chart */}
                        <SkillDistributionChart
                          mu={selectedModel.mu}
                          sigma={selectedModel.sigma}
                          exposed={selectedModel.exposed}
                          modelLabel={selectedModel.modelSlug}
                          referenceMu={referenceModel?.mu}
                          referenceSigma={referenceModel?.sigma}
                          referenceLabel={referenceModel?.modelSlug}
                          width={500}
                          height={280}
                        />

                        {/* Skill metrics */}
                        <SkillMetrics
                          mu={selectedModel.mu}
                          sigma={selectedModel.sigma}
                          exposed={selectedModel.exposed}
                        />

                        {/* Win probability (if reference selected) */}
                        {referenceModel && (
                          <WinProbability
                            compareMu={selectedModel.mu}
                            compareSigma={selectedModel.sigma}
                            compareLabel={selectedModel.modelSlug}
                            baselineMu={referenceModel.mu}
                            baselineSigma={referenceModel.sigma}
                            baselineLabel={referenceModel.modelSlug}
                          />
                        )}
                      </div>
                    ) : (
                      <div className="py-20 text-center text-sm font-semibold text-gray-500">
                        Select a model from the left list to begin.
                      </div>
                    )}
                  </Card>
                </TabsContent>

                <TabsContent value="comparison" className="mt-4 space-y-4">
                  {/* Scatter plot */}
                  <SkillScatterPlot
                    leaderboard={leaderboard}
                    selectedModels={comparisonSelections}
                    hoveredModel={hoveredModel}
                    onPointClick={handleScatterPointClick}
                    onPointHover={setHoveredModel}
                    colorPalette={MULTI_CURVE_PALETTE}
                    unselectedColor="#9CA3AF"
                    muDomain={axisDomains.muDomain}
                    sigmaDomain={axisDomains.sigmaDomain}
                  />

                  {/* Multi-curve overlay */}
                  <MultiCurveOverlay
                    models={comparisonModels}
                    hoveredModel={hoveredModel}
                    onCurveHover={setHoveredModel}
                    colorPalette={MULTI_CURVE_PALETTE}
                  />
                </TabsContent>
              </Tabs>
            </div>

            {/* RIGHT: Baseline model selector */}
            <div className="space-y-4">
              <Card className="p-4">
                <div className="mb-3">
                  <h3 className="text-sm font-bold text-gray-800">Baseline Model</h3>
                  <p className="text-xs text-gray-500">Sorted by win rate</p>
                </div>
                <input
                  type="text"
                  placeholder="Search models..."
                  value={referenceFilter}
                  onChange={(e) => setReferenceFilter(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-gray-200 rounded-md mb-2 focus:outline-none focus:ring-2 focus:ring-green-500"
                />
                <ScrollArea className="h-[280px]">
                  <div className="space-y-1">
                    {filteredForReference
                      .sort((a, b) => (b.winRate || 0) - (a.winRate || 0))
                      .map((entry) => (
                        <button
                          key={entry.modelSlug}
                          onClick={() => handleSelectReference(entry.modelSlug)}
                          className={`w-full text-left px-3 py-2 text-xs rounded-md transition-colors ${
                            entry.modelSlug === referenceSlug
                              ? 'bg-green-100 text-green-800 font-semibold'
                              : 'hover:bg-gray-100 text-gray-700'
                          }`}
                        >
                          <div className="font-medium truncate">{entry.modelSlug}</div>
                          <div className="text-gray-500">
                            {((entry.winRate || 0) * 100).toFixed(1)}% win rate - {entry.gamesPlayed} games
                          </div>
                        </button>
                      ))}
                  </div>
                </ScrollArea>
              </Card>

              {/* Reference model snapshot */}
              {referenceModel && (
                <Card className="p-4">
                  <h4 className="text-sm font-bold text-green-700 truncate">{referenceModel.modelSlug}</h4>
                  <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-gray-500">mu:</span>{' '}
                      <span className="font-mono font-semibold">{referenceModel.mu.toFixed(2)}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">sigma:</span>{' '}
                      <span className="font-mono font-semibold">{referenceModel.sigma.toFixed(2)}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">exposed:</span>{' '}
                      <span className="font-mono font-semibold">{referenceModel.exposed.toFixed(2)}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">games:</span>{' '}
                      <span className="font-mono font-semibold">{referenceModel.gamesPlayed}</span>
                    </div>
                  </div>
                </Card>
              )}
            </div>
          </div>

          {/* Educational callout */}
          <Alert className="border-blue-200 bg-blue-50">
            <AlertDescription className="text-sm text-gray-800">
              <strong>Why the difference?</strong> Win/Loss ratio shows how often a model wins, but doesn&apos;t account for
              opponent strength. TrueSkill adjusts for this. Compare a narrow curve (high confidence) against a wide curve
              (uncertain/new model).
            </AlertDescription>
          </Alert>

          {/* Empty state */}
          {leaderboard.length === 0 && (
            <Alert className="border-yellow-200 bg-yellow-50">
              <AlertDescription className="text-sm text-yellow-800">
                No leaderboard data available. Make sure the Flask backend is running.
              </AlertDescription>
            </Alert>
          )}
        </div>
      </div>
    </TooltipProvider>
  );
}
