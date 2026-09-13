protected Stamp foldStampImpl(Stamp s) {
                            if (s.isEmpty()) {
                                return s;
                            }
                            IntegerStamp stamp = (IntegerStamp) s;
                            int bits = stamp.getBits();
                            if (stamp.lowerBound == stamp.upperBound) {
                                long value = CodeUtil.convert(-stamp.lowerBound(), stamp.getBits(), false);
                                return createConstant(stamp.getBits(), value);
                            }
                            /*
                             * Two's complement negation preserves trailing zero bits: If s is of
                             * the form xx100, its negation is ~s + 1 = yy011 + 00001 = zz100. This
                             * is also true for the most negative value, whose negation is itself.
                             */
                            long newMayBeSet = ~CodeUtil.mask(Long.numberOfTrailingZeros(stamp.mayBeSet)) & CodeUtil.mask(bits);
                            if (stamp.lowerBound() != CodeUtil.minValue(bits)) {
                                return create(bits, -stamp.upperBound(), -stamp.lowerBound(), 0, newMayBeSet);
                            } else {
                                return stampForMask(bits, 0, newMayBeSet);
                            }
                        }
