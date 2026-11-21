<script setup lang="ts">
import { ArrowRight, BookOpen } from 'lucide-vue-next'
// The same picture as the README, drawn by the diagram skill from
// docs/diagrams/src/how-it-works.json. It carries its own motion and text.
import picture from '@diagrams/how-it-works-dark.svg?raw'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { blob } from '@/content'
</script>

<template>
  <section id="top" class="blueprint relative overflow-hidden">
    <div class="mx-auto flex max-w-6xl flex-col items-center gap-6 px-6 pt-20 pb-6 text-center">
      <Badge class="border-[#4a3a12] bg-[#1a1408] text-gate">A plugin for Claude Code</Badge>
      <h1 class="max-w-4xl font-display text-[clamp(40px,6.5vw,78px)] leading-[1.02] font-bold tracking-[-0.03em]">
        AI writes the code.<br><span class="text-gate">Locked tests</span> decide.
      </h1>
      <p class="max-w-2xl text-lg leading-relaxed text-muted-foreground">
        Tollgate lets an AI build changes to your software, and keeps each change out of your main
        branch until it passes tests the AI cannot touch.
      </p>
      <div class="mt-1 flex flex-wrap justify-center gap-3">
        <Button as="a" href="#start" size="lg" class="no-underline hover:text-primary-foreground">
          Get started<ArrowRight />
        </Button>
        <Button as="a" :href="blob('docs/plan.md')" variant="outline" size="lg" class="no-underline hover:text-foreground">
          <BookOpen />Read the plan
        </Button>
      </div>
    </div>
    <!-- On a phone the picture keeps a readable size and scrolls sideways. -->
    <div class="mx-auto max-w-[1180px] overflow-x-auto px-4 pb-12">
      <div class="hero-picture min-w-[720px]" v-html="picture" />
    </div>
  </section>
</template>
