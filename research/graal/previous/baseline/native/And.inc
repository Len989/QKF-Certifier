protected Stamp foldStampImpl(Stamp stamp1, Stamp stamp2) {
                            if (stamp1.isEmpty()) {
                                return stamp1;
                            }
                            if (stamp2.isEmpty()) {
                                return stamp2;
                            }
                            IntegerStamp a = (IntegerStamp) stamp1;
                            IntegerStamp b = (IntegerStamp) stamp2;
                            assert a.getBits() == b.getBits() : "Bits must match " + Assertions.errorMessageContext("a", a, "b", b);

                            int bits = a.getBits();
                            long mustBeSet = a.mustBeSet & b.mustBeSet;
                            long mayBeSet = a.mayBeSet & b.mayBeSet;
                            if (significantBit(bits, mayBeSet) == 0) {
                                /*
                                 * The result will be positive. Try to refine the bounds. We can
                                 * only exploit positive bounds, and one of the inputs may be
                                 * negative. For example, for [-20, -10] & [10, 20] we can use the
                                 * positive 20 as an upper bound for the result, but the other
                                 * value's upper bound -10 gives no useful information.
                                 */
                                long upperBound = maxValueForMasks(bits, mustBeSet, mayBeSet);
                                if (a.lowerBound >= 0) {
                                    upperBound = Math.min(upperBound, a.upperBound);
                                }
                                if (b.lowerBound >= 0) {
                                    upperBound = Math.min(upperBound, b.upperBound);
                                }
                                return create(bits, 0, upperBound, mustBeSet, mayBeSet);
                            } else if (significantBit(bits, mustBeSet) == 1) {
                                /*
                                 * The result will be negative. Try to refine the bounds. Both upper
                                 * bounds must be negative, so we can exploit both.
                                 */
                                long upperBound = Math.min(maxValueForMasks(bits, mustBeSet, mayBeSet), Math.min(a.upperBound, b.upperBound));
                                return create(bits, minValueForMasks(bits, mustBeSet, mayBeSet), upperBound, mustBeSet, mayBeSet);
                            }
                            return stampForMask(bits, mustBeSet, mayBeSet);
                        }
