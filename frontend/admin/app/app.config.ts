export default defineAppConfig({
  ui: {
    icons: {
      close: 'operator-close',
      loading: 'operator-loading',
      check: 'operator-check',
      chevronDown: 'operator-chevron-down',
      chevronLeft: 'operator-chevron-left',
      chevronRight: 'operator-chevron-right',
      arrowRight: 'operator-arrow-right',
      menu: 'operator-menu',
    },
    colors: {
      primary: 'cobalt',
      secondary: 'cobalt',
      success: 'turquoise',
      info: 'cobalt',
      warning: 'cobalt',
      error: 'raspberry',
      neutral: 'slate',
    },
    button: {
      slots: { base: 'rounded-[7px]' },
      compoundVariants: [
        {
          color: 'primary',
          variant: 'solid',
          class:
            'bg-[#3454D1] text-white hover:bg-[#2843B0] active:bg-[#23398D]',
        },
        {
          color: 'success',
          variant: 'solid',
          class: 'bg-[#34D1BF] text-[#070707] hover:bg-[#65DDCC]',
        },
        {
          color: 'error',
          variant: 'solid',
          class: 'bg-[#D1345B] text-white hover:bg-[#B52349]',
        },
      ],
    },
    card: {
      slots: {
        root: 'rounded-[11px] shadow-none',
        header: 'px-5 py-4',
        body: 'p-5',
        footer: 'px-5 py-4',
      },
    },
  },
})
