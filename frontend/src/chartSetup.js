// Chart.js is registered once, centrally, and only with the pieces the app uses
// (plan: "register only used controllers"). Importing controllers/elements that
// are never drawn is dead weight in the bundle, which matters on a small VM.
import {
  Chart,
  LineController,
  BarController,
  LineElement,
  PointElement,
  BarElement,
  CategoryScale,
  LinearScale,
  LogarithmicScale,
  Filler,
  Tooltip,
  Legend,
} from 'chart.js'

Chart.register(
  LineController,
  BarController,
  LineElement,
  PointElement,
  BarElement,
  CategoryScale,
  LinearScale,
  LogarithmicScale,
  Filler,
  Tooltip,
  Legend,
)

// Global defaults that keep the demo smooth and payload-small.
Chart.defaults.animation = false
Chart.defaults.normalized = true
Chart.defaults.plugins.legend.labels.boxWidth = 12

export { Chart }
