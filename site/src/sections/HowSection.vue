<script setup lang="ts">
import { Lock } from 'lucide-vue-next'
import SectionHead from '@/components/SectionHead.vue'

const steps = [
  { n: '01', tone: 'text-you', title: 'You ask', text: 'In plain words. Tollgate writes a plan, and fresh AIs check it before it is cut into small tickets.' },
  { n: '02', tone: 'text-github', title: 'Tests are locked', text: 'A separate AI writes one test for each must-have item. GitHub locks them before any code exists.' },
  { n: '03', tone: 'text-ai', title: 'The AI builds', text: 'It tries until the locked tests pass. It keeps its best attempt, and stops after 3 tries or the same failure twice.' },
  { n: '04', tone: 'text-gate', title: 'The gate decides', text: 'A program with no AI checks the ticket, the plan, the locked files, the tier, and the tests. When the AI is stuck, the advisor decides: a second AI, or you.' },
  { n: '05', tone: 'text-github', title: 'GitHub runs it again', text: "The tests run again with the main branch's harness, and a model reviews the riskier changes. Then the change merges." },
]
</script>

<template>
  <section id="how" class="border-t border-line bg-panel">
    <div class="mx-auto grid max-w-6xl items-start gap-14 px-6 py-24 lg:grid-cols-2">
      <div class="flex flex-col gap-5 lg:sticky lg:top-24">
        <SectionHead eyebrow="How it works" title="Think of an exam." tone="ai">
          <p>
            The questions are set and sealed before the student starts. The student can take the
            exam more than once, but cannot rewrite the questions or mark the paper.
          </p>
        </SectionHead>
        <div class="flex items-center gap-2.5 rounded-lg border border-border bg-card px-4 py-3.5 text-sm text-body">
          <Lock class="size-5 shrink-0 text-[#7ee787]" aria-hidden="true" />
          Locked tests cannot be edited, skipped, or removed.
        </div>
      </div>
      <ol class="m-0 list-none p-0">
        <li v-for="s in steps" :key="s.n" class="grid grid-cols-[64px_1fr] gap-5 border-t border-line py-6">
          <span :class="['pt-1 font-mono text-sm tracking-[0.12em]', s.tone]">{{ s.n }}</span>
          <div class="flex flex-col gap-1.5">
            <h3 class="font-display text-[22px] font-semibold">{{ s.title }}</h3>
            <p class="max-w-xl leading-relaxed text-muted-foreground">{{ s.text }}</p>
          </div>
        </li>
      </ol>
    </div>
  </section>
</template>
