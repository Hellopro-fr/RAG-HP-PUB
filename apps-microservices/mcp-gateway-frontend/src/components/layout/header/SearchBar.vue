<template>
  <div class="hidden lg:block">
    <form @submit.prevent>
      <div class="relative">
        <button class="absolute -translate-y-1/2 left-4 top-1/2" type="button">
          <i class="pi pi-search text-gray-500 dark:text-gray-400" />
        </button>
        <input
          type="text"
          placeholder="Rechercher..."
          class="dark:bg-dark-900 h-11 w-full rounded-lg border border-gray-200 bg-transparent py-2.5 pl-12 pr-14 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-800 dark:bg-gray-900 dark:bg-white/[0.03] dark:text-white/90 dark:placeholder:text-white/30 dark:focus:border-brand-800 xl:w-[430px]"
        />
        <button
          type="button"
          class="absolute right-2.5 top-1/2 inline-flex -translate-y-1/2 items-center gap-0.5 rounded-lg border border-gray-200 bg-gray-50 px-[7px] py-[4.5px] text-xs -tracking-[0.2px] text-gray-500 dark:border-gray-800 dark:bg-white/[0.03] dark:text-gray-400"
        >
          <span>&#8984;</span>
          <span>K</span>
        </button>
      </div>
    </form>
  </div>
</template>
