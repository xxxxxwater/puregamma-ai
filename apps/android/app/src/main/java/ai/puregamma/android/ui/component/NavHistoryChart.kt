package ai.puregamma.android.ui.component

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ai.puregamma.android.model.NavPoint
import ai.puregamma.android.ui.*
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.roundToInt

enum class NavChartRange(val label: String, val days: Int) {
    D1("1D", 1),
    W1("1W", 7),
    M1("1M", 30),
    ALL("ALL", Int.MAX_VALUE),
}

@Composable
fun NavHistoryChart(
    points: List<NavPoint>,
    modifier: Modifier = Modifier,
) {
    if (points.isEmpty()) return

    var selectedRange by remember { mutableStateOf(NavChartRange.ALL) }
    var crosshairIndex by remember { mutableStateOf<Int?>(null) }

    val now = Instant.now()
    val cutoff = now.minus(selectedRange.days.toLong(), ChronoUnit.DAYS)
    val filtered = if (selectedRange == NavChartRange.ALL) points
    else points.filter { it.date >= cutoff }

    val sortedPoints = remember(filtered) { filtered.sortedBy { it.date } }
    val values = remember(sortedPoints) { sortedPoints.map { it.value } }
    val minVal = remember(values) { values.minOrNull() ?: 0.0 }
    val maxVal = remember(values) { values.maxOrNull() ?: 1.0 }
    val range = remember(minVal, maxVal) { max(maxVal - minVal, 1.0) }

    val primaryColor = Color(0xFFD6B35A)
    val accentColor = Color(0xFFF4F4F5)
    val greenFill = Color(0x22D9F99D)

    Column(modifier.fillMaxWidth()) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("NAV History", style = MaterialTheme.typography.titleMedium)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                NavChartRange.entries.forEach { rangeVal ->
                    val selected = selectedRange == rangeVal
                    Text(
                        text = rangeVal.label,
                        color = if (selected) accentColor else MaterialTheme.colorScheme.onSurfaceVariant,
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier
                            .clip(RoundedCornerShape(4.dp))
                            .then(
                                if (selected) Modifier.background(Color(0x22FFFFFF), RoundedCornerShape(4.dp))
                                else Modifier
                            )
                            .padding(horizontal = 8.dp, vertical = 4.dp)
                            .let { if (!selected) it else it },
                    )
                    if (!selected) {
                        Text(
                            text = rangeVal.label,
                            color = if (selected) accentColor else MaterialTheme.colorScheme.onSurfaceVariant,
                            style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier
                                .padding(horizontal = 8.dp, vertical = 4.dp),
                        )
                    }
                }
            }
        }

        Spacer(Modifier.height(8.dp))

        val chartHeight = 180.dp
        val density = LocalDensity.current
        val chartHeightPx = with(density) { chartHeight.toPx() }

        Canvas(
            modifier = Modifier
                .fillMaxWidth()
                .height(chartHeight)
                .padding(horizontal = 16.dp)
                .pointerInput(sortedPoints) {
                    detectTapGestures { offset ->
                        val index = resolveIndex(offset.x, size.width.toFloat(), sortedPoints.size)
                        crosshairIndex = if (crosshairIndex == index) null else index
                    }
                }
                .pointerInput(sortedPoints) {
                    detectHorizontalDragGestures(
                        onDragEnd = { crosshairIndex = null },
                        onHorizontalDrag = { _, dragAmount ->
                            if (sortedPoints.isEmpty()) return@detectHorizontalDragGestures
                            val current = crosshairIndex ?: (sortedPoints.size / 2)
                            val step = -dragAmount / (size.width / sortedPoints.size.coerceAtLeast(1))
                            crosshairIndex = (current + step.roundToInt())
                                .coerceIn(0, sortedPoints.size - 1)
                        },
                    )
                },
        ) {
            val padding = 40f
            val drawWidth = size.width - padding * 2
            val drawHeight = size.height - padding * 2

            if (drawWidth <= 0 || drawHeight <= 0) return@Canvas

            val baselinePx = padding
            val topPx = padding + drawHeight

            fun xForIndex(index: Int): Float {
                val ratio = if (sortedPoints.size <= 1) 0.5f
                else index.toFloat() / (sortedPoints.size - 1)
                return padding + ratio * drawWidth
            }

            fun yForValue(value: Double): Float {
                val ratio = ((value - minVal) / range).toFloat()
                return topPx - ratio * drawHeight
            }

            val gridColor = Color(0x15FFFFFF)
            for (i in 0..3) {
                val y = padding + drawHeight * i / 3
                drawLine(gridColor, Offset(padding, y), Offset(padding + drawWidth, y), 1f)
            }

            if (sortedPoints.size >= 2) {
                val path = Path()
                sortedPoints.forEachIndexed { index, point ->
                    val x = xForIndex(index)
                    val y = yForValue(point.value)
                    if (index == 0) path.moveTo(x, y) else path.lineTo(x, y)
                }
                drawPath(path, accentColor, style = Stroke(2f))

                val fillPath = Path()
                fillPath.addPath(path)
                val lastX = xForIndex(sortedPoints.lastIndex)
                fillPath.lineTo(lastX, topPx)
                fillPath.lineTo(xForIndex(0), topPx)
                fillPath.close()
                drawPath(fillPath, Brush.verticalGradient(listOf(greenFill, Color.Transparent)))
            }

            crosshairIndex?.let { idx ->
                if (idx in sortedPoints.indices) {
                    val point = sortedPoints[idx]
                    val cx = xForIndex(idx)
                    val cy = yForValue(point.value)

                    drawLine(accentColor.copy(alpha = 0.4f), Offset(cx, padding), Offset(cx, topPx), 1f)
                    drawCircle(accentColor, 5f, Offset(cx, cy))
                    drawCircle(Color(0xFF030303), 3f, Offset(cx, cy))

                    val tooltipText = formatMoney(point.value)
                    val tooltipDate = formatDate(point.date)

                    val textPaint = android.graphics.Paint().apply {
                        color = android.graphics.Color.WHITE
                        textSize = 26f
                        isAntiAlias = true
                        typeface = android.graphics.Typeface.MONOSPACE
                    }
                    val datePaint = android.graphics.Paint().apply {
                        color = android.graphics.Color.argb(180, 255, 255, 255)
                        textSize = 22f
                        isAntiAlias = true
                    }

                    val textWidth = textPaint.measureText(tooltipText)
                    val dateWidth = datePaint.measureText(tooltipDate)
                    val boxWidth = max(textWidth, dateWidth) + 20f
                    val boxHeight = 50f

                    val boxX = if (cx + boxWidth / 2 > size.width - 4f) size.width - boxWidth - 4f
                    else if (cx - boxWidth / 2 < 4f) 4f
                    else cx - boxWidth / 2

                    drawContext.canvas.nativeCanvas.apply {
                        drawRoundRect(boxX, 8f, boxX + boxWidth, 8f + boxHeight, 6f, 6f,
                            android.graphics.Paint().apply {
                                color = android.graphics.Color.argb(220, 3, 3, 3)
                                style = android.graphics.Paint.Style.FILL
                                isAntiAlias = true
                            })
                        drawRoundRect(boxX, 8f, boxX + boxWidth, 8f + boxHeight, 6f, 6f,
                            android.graphics.Paint().apply {
                                color = android.graphics.Color.argb(40, 255, 255, 255)
                                style = android.graphics.Paint.Style.STROKE
                                strokeWidth = 1f
                                isAntiAlias = true
                            })
                        drawText(tooltipText, boxX + 10f, 30f, textPaint)
                        drawText(tooltipDate, boxX + 10f, 50f, datePaint)
                    }
                }
            }
        }
    }
}

private fun resolveIndex(x: Float, width: Float, count: Int): Int {
    if (count <= 1 || width <= 0) return 0
    val step = width / (count - 1)
    return ((x - 40f) / step).roundToInt().coerceIn(0, count - 1)
}

private val _isoDateFormatter = DateTimeFormatter.ofPattern("MM/dd HH:mm")
    .withZone(ZoneId.systemDefault())

private fun formatDate(instant: Instant): String = _isoDateFormatter.format(instant)

private fun formatMoney(value: Double): String {
    val nf = java.text.NumberFormat.getCurrencyInstance(java.util.Locale.US)
    nf.currency = java.util.Currency.getInstance("USD")
    return nf.format(value)
}
