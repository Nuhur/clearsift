import { ColorType, LineSeries, createChart } from 'lightweight-charts'
import { useEffect, useRef } from 'react'
import type { PricePointOut } from '../api'
import { priceSummary } from '../lib/prices'

/** A year of closing prices as a plain line. */
export function PriceChart({ prices }: { prices: PricePointOut[] }) {
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const element = box.current
    if (element === null) return
    const chart = createChart(element, {
      autoSize: true,
      // credited in a line under the chart instead, so it doesn't sit on top of the line
      layout: { attributionLogo: false },
      // nothing to drag or zoom, it's a quick look at the year
      handleScroll: false,
      handleScale: false,
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
    })
    const series = chart.addSeries(LineSeries, {
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    })
    series.setData(prices.map((p) => ({ time: p.date, value: p.close })))
    chart.timeScale().fitContent()

    // the canvas can't use CSS variables, so copy the colours over now and on every theme switch
    const paint = () => {
      const styles = getComputedStyle(document.documentElement)
      const token = (name: string) => styles.getPropertyValue(name).trim()
      chart.applyOptions({
        layout: {
          background: { type: ColorType.Solid, color: 'transparent' },
          textColor: token('--muted'),
          fontFamily: styles.fontFamily,
        },
        crosshair: {
          vertLine: { color: token('--line3'), labelBackgroundColor: token('--ink') },
          horzLine: { color: token('--line3'), labelBackgroundColor: token('--ink') },
        },
      })
      series.applyOptions({ color: token('--lapis') })
    }
    paint()
    const watcher = new MutationObserver(paint)
    watcher.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })

    return () => {
      watcher.disconnect()
      chart.remove()
    }
  }, [prices])

  return <div ref={box} role="img" aria-label={priceSummary(prices)} className="h-52 w-full" />
}
