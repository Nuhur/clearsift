// Exact decimal sums for money, so float noise never moves an amount by a penny.

interface Decimal {
  // the digits as a whole number, e.g. 98n for 0.0098
  digits: bigint
  // how many of those digits sit after the point, e.g. 4 for 0.0098
  scale: number
}

/** Read a number the way Python's Decimal(str(x)) does, from its shortest written form. */
export function toDecimal(value: number): Decimal {
  if (!Number.isFinite(value)) throw new RangeError(`not a finite number: ${value}`)
  // String() gives the shortest form that reads back as the same number, like Python's str()
  const [mantissa, exponentText] = String(value).toLowerCase().split('e')
  const exponent = exponentText === undefined ? 0 : Number(exponentText)
  const negative = mantissa.startsWith('-')
  const [whole, fraction = ''] = mantissa.replace('-', '').split('.')
  let digits = BigInt(whole + fraction)
  let scale = fraction.length - exponent
  if (scale < 0) {
    digits *= 10n ** BigInt(-scale)
    scale = 0
  }
  return { digits: negative ? -digits : digits, scale }
}

/** Multiply two decimals exactly. */
export function multiply(a: Decimal, b: Decimal): Decimal {
  return { digits: a.digits * b.digits, scale: a.scale + b.scale }
}

/** Round a non-negative decimal up to the given places, as a whole number of those units. */
export function ceilTo(value: Decimal, places: number): bigint {
  if (value.digits < 0n) throw new RangeError('only rounds amounts of zero or more')
  if (value.scale <= places) return value.digits * 10n ** BigInt(places - value.scale)
  const step = 10n ** BigInt(value.scale - places)
  const units = value.digits / step
  return value.digits % step === 0n ? units : units + 1n
}

/** Write a whole number of hundredths as text, e.g. 49n as "0.49". */
export function hundredths(units: bigint): string {
  const text = units.toString().padStart(3, '0')
  return `${text.slice(0, -2)}.${text.slice(-2)}`
}
