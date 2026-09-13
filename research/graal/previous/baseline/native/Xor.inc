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
                            if (b.lowerBound == -1 && b.upperBound == -1) {
                                /*
                                 * This is a bitwise negation. Fold with the Not op which takes
                                 * bounds into account, unlike the code below which only uses the
                                 * masks.
                                 */
                                return OPS.getNot().foldStamp(a);
                            } else if (a.lowerBound == -1 && a.upperBound == -1) {
                                return OPS.getNot().foldStamp(b);
                            }

                            long variableBits = (a.mustBeSet() ^ a.mayBeSet()) | (b.mustBeSet() ^ b.mayBeSet());
                            long newMustBeSet = (a.mustBeSet() ^ b.mustBeSet()) & ~variableBits;
                            long newMayBeSet = (a.mustBeSet() ^ b.mustBeSet()) | variableBits;
                            return stampForMask(a.getBits(), newMustBeSet, newMayBeSet);
                        }
