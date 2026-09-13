/*
 * Copyright (c) 2012, 2026, Oracle and/or its affiliates. All rights reserved.
 * DO NOT ALTER OR REMOVE COPYRIGHT NOTICES OR THIS FILE HEADER.
 *
 * This code is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License version 2 only, as
 * published by the Free Software Foundation.  Oracle designates this
 * particular file as subject to the "Classpath" exception as provided
 * by Oracle in the LICENSE file that accompanied this code.
 *
 * This code is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
 * version 2 for more details (a copy is included in the LICENSE file that
 * accompanied this code).
 *
 * You should have received a copy of the GNU General Public License version
 * 2 along with this work; if not, write to the Free Software Foundation,
 * Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA.
 *
 * Please contact Oracle, 500 Oracle Parkway, Redwood Shores, CA 94065 USA
 * or visit www.oracle.com if you need additional information or have any
 * questions.
 */

// Local dependency shims, not upstream Graal runtime classes.
import java.io.*;
abstract class Stamp { abstract boolean hasValues(); final boolean isEmpty(){return !hasValues();} }
abstract class PrimitiveStamp extends Stamp {
  private final int bits; PrimitiveStamp(int bits,Object ops){this.bits=bits;}
  int getBits(){return bits;}
}
class CodeUtil {
  static long mask(int bits){return bits==64 ? -1L : (1L<<bits)-1;}
  static long minValue(int bits){return bits==64 ? Long.MIN_VALUE : -(1L<<(bits-1));}
  static long maxValue(int bits){return bits==64 ? Long.MAX_VALUE : (1L<<(bits-1))-1;}
  static long signExtend(long v,int bits){return bits==64 ? v : (v<<(64-bits))>>(64-bits);}
  static long convert(long v,int bits,boolean unsigned){return unsigned ? v&mask(bits) : signExtend(v,bits);}
  static boolean isPowerOf2(long v){return v>0 && (v&(v-1))==0;}
}
class Assertions { static String errorMessageContext(Object... args){return java.util.Arrays.toString(args);} }
class GraalError {
  static void guarantee(boolean p,String message,Object... args){if(!p)throw new IllegalStateException(String.format(message,args));}
  static RuntimeException shouldNotReachHere(String s){return new IllegalStateException(s);}
}
class IntegerStamp extends PrimitiveStamp {
  private final long lowerBound,upperBound,mustBeSet,mayBeSet;
  private final boolean canBeZero;
  static final int ITERATION_LIMIT=3;
  static final Ops OPS=new Ops();
  static IntegerStamp create(int bits){return new IntegerStamp(bits,false);}
  static IntegerStamp createEmptyStamp(int bits){return new IntegerStamp(bits,true);}
  static boolean isPowerOf2(long v){return CodeUtil.isPowerOf2(v);}
  static class Ops {
    Op getAdd(){return new Op("add");} Op getNeg(){return new Op("neg");} Op getNot(){return new Op("not");}
  }
  static class Op {
    final String name; Op(String n){name=n;}
    Stamp foldStamp(Stamp a,Stamp b){return foldAdd(a,b);}
    Stamp foldStamp(Stamp a){return name.equals("neg") ? foldNeg(a) : foldNot(a);}
  }
private IntegerStamp(int bits, boolean empty) {
        super(bits, OPS);
        if (empty) {
            this.lowerBound = CodeUtil.maxValue(bits);
            this.upperBound = CodeUtil.minValue(bits);
            this.mustBeSet = CodeUtil.mask(bits);
            this.mayBeSet = 0;
            this.canBeZero = false;
        } else {
            this.lowerBound = CodeUtil.minValue(bits);
            this.upperBound = CodeUtil.maxValue(bits);
            this.mustBeSet = 0;
            this.mayBeSet = CodeUtil.mask(bits);
            this.canBeZero = true;
        }
    }

private IntegerStamp(int bits, long constant) {
        this(bits, constant, constant, constant & CodeUtil.mask(bits), constant & CodeUtil.mask(bits), constant == 0);
    }

private IntegerStamp(int bits, long lowerBound, long upperBound) {
        super(bits, OPS);
        int sameBitCount = Long.numberOfLeadingZeros(lowerBound ^ upperBound);
        long sameBitMask = -1L >>> sameBitCount;
        long defaultMask = CodeUtil.mask(bits);

        this.lowerBound = lowerBound;
        this.upperBound = upperBound;
        this.mustBeSet = defaultMask & (lowerBound & ~sameBitMask);
        this.mayBeSet = defaultMask & (lowerBound | sameBitMask);

        this.canBeZero = contains(0, true);
        assert checkInvariants();
    }

private IntegerStamp(int bits, long lowerBound, long upperBound, long mustBeSet, long mayBeSet, boolean canBeZero) {
        super(bits, OPS);

        this.lowerBound = lowerBound;
        this.upperBound = upperBound;
        this.mustBeSet = mustBeSet;
        this.mayBeSet = mayBeSet;

        // use ctor param because canBeZero is not set yet
        this.canBeZero = contains(0, canBeZero);
        assert checkInvariants();
    }

private boolean checkInvariants() {
        final int allowedBitsMask = 1 | 8 | 16 | 32 | 64;
        assert (getBits() & allowedBitsMask) == getBits() && CodeUtil.isPowerOf2(getBits()) : "unexpected bit size: " + getBits();
        assert lowerBound >= CodeUtil.minValue(getBits()) : this;
        assert upperBound <= CodeUtil.maxValue(getBits()) : this;
        assert (mustBeSet & CodeUtil.mask(getBits())) == mustBeSet : this;
        assert (mayBeSet & CodeUtil.mask(getBits())) == mayBeSet : this;
        // Check for valid masks or the empty encoding
        assert (mustBeSet & ~mayBeSet) == 0 || (mayBeSet == 0 && mustBeSet == CodeUtil.mask(getBits())) : String.format("must: %016x may: %016x", mustBeSet, mayBeSet);
        assert !this.canBeZero || contains(0) : " Stamp " + this + " either has canBeZero set to false or needs to contain 0";
        assert !isEmpty() : String.format("unexpected empty stamp: %s %s %s %s %s %s", lowerBound, upperBound, mustBeSet, mayBeSet, canBeZero, this);
        assert contains(upperBound) : String.format("%s must contain its upper bound", this);
        assert contains(lowerBound) : String.format("%s must contain its lower bound", this);
        return true;
    }

public static IntegerStamp createConstant(int bits, long value) {
        return new IntegerStamp(bits, value);
    }

public static IntegerStamp create(int bits, long lowerBoundInput, long upperBoundInput) {
        if (lowerBoundInput > upperBoundInput) {
            return createEmptyStamp(bits);
        }

        if (lowerBoundInput == upperBoundInput) {
            return createConstant(bits, lowerBoundInput);
        }

        return new IntegerStamp(bits, lowerBoundInput, upperBoundInput);
    }

public static IntegerStamp create(int bits, long lowerBoundInput, long upperBoundInput, long mustBeSet, long mayBeSet) {
        return create(bits, lowerBoundInput, upperBoundInput, mustBeSet, mayBeSet, true);
    }

public static IntegerStamp create(int bits, long lowerBoundInput, long upperBoundInput, long mustBeSetInput, long mayBeSetInput, boolean canBeZero) {
        assert lowerBoundInput >= CodeUtil.minValue(bits) && lowerBoundInput <= CodeUtil.maxValue(bits) : Assertions.errorMessageContext("bits", bits, "lowerBound", lowerBoundInput, "upperBound",
                        upperBoundInput, "mustBeSetInput", mustBeSetInput, "mayBeSetInput", mayBeSetInput, "canBeZero", canBeZero);
        assert upperBoundInput >= CodeUtil.minValue(bits) && upperBoundInput <= CodeUtil.maxValue(bits) : Assertions.errorMessageContext("bits", bits, "lowerBound", lowerBoundInput, "upperBound",
                        upperBoundInput, "mustBeSetInput", mustBeSetInput, "mayBeSetInput", mayBeSetInput, "canBeZero", canBeZero);

        if (isEmpty(lowerBoundInput, upperBoundInput, mustBeSetInput, mayBeSetInput)) {
            return createEmptyStamp(bits);
        }

        long defaultMask = CodeUtil.mask(bits);

        if (mustBeSetInput == 0 && mayBeSetInput == defaultMask && canBeZero) {
            return create(bits, lowerBoundInput, upperBoundInput);
        }

        long lowerBoundCurrent = lowerBoundInput;
        long upperBoundCurrent = upperBoundInput;
        long mustBeSetCurrent = mustBeSetInput;
        long mayBeSetCurrent = mayBeSetInput;

        int iterations = 0;
        while (iterations++ < ITERATION_LIMIT) {

            // Set lower bound, use masks to make it more precise
            long minValue = minValueForMasks(bits, mustBeSetCurrent, mayBeSetCurrent);
            long lowerBoundTmp = Math.max(lowerBoundCurrent, minValue);

            // Set upper bound, use masks to make it more precise
            long maxValue = maxValueForMasks(bits, mustBeSetCurrent, mayBeSetCurrent);
            long upperBoundTmp = Math.min(upperBoundCurrent, maxValue);

            // Compute masks with the new bounds in mind.
            final long boundedMustBeSet;
            final long boundedMayBeSet;
            if (lowerBoundTmp == upperBoundTmp) {
                // For constants the masks are just the value
                boundedMustBeSet = lowerBoundTmp;
                boundedMayBeSet = lowerBoundTmp;
            } else {
                /*
                 * Any high bits that are the same between the upper and lower bound can be used to
                 * refine the mayBeSet and mustBeSet. xor'ing the bounds produces leading zeros for
                 * these bits.
                 */
                int sameBitCount = Long.numberOfLeadingZeros(lowerBoundTmp ^ upperBoundTmp);
                long sameBitMask = -1L >>> sameBitCount;
                boundedMayBeSet = lowerBoundTmp | sameBitMask;
                boundedMustBeSet = lowerBoundTmp & ~sameBitMask;
            }

            long mustBeSetTmp = defaultMask & (mustBeSetCurrent | boundedMustBeSet);
            long mayBeSetTmp = defaultMask & mayBeSetCurrent & boundedMayBeSet;

            // Now recompute the bounds from any adjustments to the may and must masks
            upperBoundTmp = Math.min(upperBoundTmp, maxValueForMasks(bits, mustBeSetTmp, mayBeSetTmp));
            lowerBoundTmp = Math.max(lowerBoundTmp, minValueForMasks(bits, mustBeSetTmp, mayBeSetTmp));

            upperBoundTmp = computeUpperBound(bits, upperBoundTmp, mustBeSetTmp, mayBeSetTmp, canBeZero);
            lowerBoundTmp = computeLowerBound(bits, lowerBoundTmp, mustBeSetTmp, mayBeSetTmp, canBeZero);

            if (lowerBoundTmp > upperBoundTmp || (mustBeSetTmp & (~mayBeSetTmp)) != 0 || (mayBeSetTmp == 0 && (lowerBoundTmp > 0 || upperBoundTmp < 0))) {
                return createEmptyStamp(bits);
            }

            if (lowerBoundCurrent == lowerBoundTmp && upperBoundCurrent == upperBoundTmp && mustBeSetCurrent == mustBeSetTmp && mayBeSetCurrent == mayBeSetTmp) {
                // The values have reached a stable state. If the incoming values are unchanged then
                // this completes in a single pass but if they change then another iteration is
                // performed to ensure the values have stabilized.
                return new IntegerStamp(bits, lowerBoundTmp, upperBoundTmp, mustBeSetTmp, mayBeSetTmp, canBeZero);
            }

            GraalError.guarantee(lowerBoundTmp >= lowerBoundCurrent, "lower bound can't get smaller: %s < %s", lowerBoundTmp, lowerBoundCurrent);
            GraalError.guarantee(upperBoundTmp <= upperBoundCurrent, "upper bound can't get larger: %s > %s", upperBoundTmp, upperBoundCurrent);

            lowerBoundCurrent = lowerBoundTmp;
            upperBoundCurrent = upperBoundTmp;
            mustBeSetCurrent = mustBeSetTmp;
            mayBeSetCurrent = mayBeSetTmp;
        }
        throw GraalError.shouldNotReachHere("More than " + ITERATION_LIMIT + "iterations required to reach a stable stamp");
    }

private static boolean isEmpty(long lowerBound, long upperBound, long mustBeSet, long mayBeSet) {
        return lowerBound > upperBound || (mustBeSet & (~mayBeSet)) != 0 || (mayBeSet == 0 && (lowerBound > 0 || upperBound < 0));
    }

private static long significantBit(long bits, long value) {
        return (value >>> (bits - 1)) & 1;
    }

private static long minValueForMasks(int bits, long mustBeSet, long mayBeSet) {
        if (significantBit(bits, mayBeSet) == 0) {
            // Value is always positive. Minimum value always positive.
            assert significantBit(bits, mustBeSet) == 0 : String.format("must: %016x may: %016x", mustBeSet, mayBeSet);
            return mustBeSet;
        } else {
            // Value can be positive or negative. Minimum value always negative.
            return mustBeSet | (-1L << (bits - 1));
        }
    }

private static long maxValueForMasks(int bits, long mustBeSet, long mayBeSet) {
        if (significantBit(bits, mustBeSet) == 1) {
            // Value is always negative. Maximum value always negative.
            assert significantBit(bits, mayBeSet) == 1 : Assertions.errorMessageContext("bits", bits, "mayBeSet", mayBeSet);
            return CodeUtil.signExtend(mayBeSet, bits);
        } else {
            // Value can be positive or negative. Maximum value always positive.
            return mayBeSet & (CodeUtil.mask(bits) >>> 1);
        }
    }

private static long computeUpperBound(int bits, long upperBound, long mustBeSet, long mayBeSet, boolean canBeZero) {
        // Start with the sign extended mustBeSet. That will be the smallest positive or negative
        // value.
        long newUpperBound = CodeUtil.signExtend(mustBeSet, bits);
        if (upperBound < 0 || newUpperBound > upperBound) {
            // If the upper bound is negative or it's positive but greater than the least
            // positive value, then start from the minimum negative value
            newUpperBound = minValueForMasks(bits, mustBeSet, mayBeSet);
        }
        // Compute the bits which are set in the mayBeSet but not the mustBeSet, ignoring the sign
        // bit which was handled above.
        newUpperBound = setOptionalBits(bits, upperBound, mustBeSet, mayBeSet, newUpperBound);

        if (newUpperBound == 0 && !canBeZero) {
            // The actual upper bound must be negative
            if (significantBit(bits, mayBeSet) == 0) {
                // All values are positive so return the minimum value.
                return CodeUtil.minValue(bits);
            } else {
                // Choose the max negative value
                newUpperBound = maxValueForMasks(bits, mustBeSet | (1L << bits - 1), mayBeSet);
            }
        }

        if (newUpperBound > upperBound) {
            // The smallest upper bound that's compatible with the masks is larger than the expected
            // upper bound, so return the minimum value.
            return CodeUtil.minValue(bits);
        }
        return newUpperBound;
    }

private static long setOptionalBits(int bits, long bound, long mustBeSet, long mayBeSet, long initialValue) {
        final long optionalBits = mayBeSet & ~mustBeSet & CodeUtil.mask(bits - 1);
        assert (initialValue & optionalBits) == 0 : Assertions.errorMessageContext("bits", bits, "bound", bound, "mustBeSet", mustBeSet, "mayBeSet", mayBeSet, "initialValue", initialValue);
        long value = initialValue;
        for (int position = bits - 1; position >= 0; position--) {
            long bit = 1L << position;
            if ((bit & optionalBits) != 0 && (value | bit) <= bound) {
                value |= bit;
            }
        }
        return value;
    }

private static long computeLowerBound(int bits, long lowerBound, long mustBeSet, long mayBeSet, boolean canBeZero) {
        long newLowerBound = minValueForMasks(bits, mustBeSet, mayBeSet);
        final long optionalBits = mayBeSet & ~mustBeSet & CodeUtil.mask(bits - 1);
        if (newLowerBound < lowerBound) {
            if (optionalBits == 0) {
                newLowerBound = 0;
            } else {
                // First find the largest value which is less than or equal to the current bound
                for (int position = bits - 1; position >= 0; position--) {
                    long bit = 1L << position;
                    if ((bit & optionalBits) != 0) {
                        if (newLowerBound + bit >= lowerBound) {
                            newLowerBound += bit;
                        }
                    }
                }
                GraalError.guarantee(newLowerBound <= lowerBound, "should have been sufficient");
                if (newLowerBound < lowerBound) {
                    // Increment the first optional bit and then adjust the bits upward until it's
                    // compatible with the masks
                    boolean incremented = false;
                    for (int position = 0; position < bits - 1; position++) {
                        long bit = 1L << position;
                        if (incremented) {
                            // We have to propagate any carried bit that changed any bits which must
                            // be set or cleared.
                            if ((bit & mustBeSet) != 0 && (newLowerBound & bit) == 0) {
                                // A mustBeSet bit has been cleared so set it
                                newLowerBound |= bit;
                            }
                            if ((bit & mayBeSet) == 0 && (newLowerBound & bit) != 0) {
                                // A bit has carried into the clear section so it needs to propagate
                                // into an mayBeSet bit.
                                newLowerBound += bit;
                            }
                        } else if ((bit & optionalBits) != 0) {
                            newLowerBound += bit;
                            incremented = true;
                        }
                    }
                }
            }
        }
        if (newLowerBound == 0 && !canBeZero) {
            // The actual upper bound must positive
            if (mustBeSet > 0) {
                newLowerBound = mustBeSet;
            } else if (mustBeSet == 0) {
                int lowBit = Long.numberOfTrailingZeros(mayBeSet);
                newLowerBound = 1L << lowBit;
            } else {
                // There is no positive value which is compatible with the masks to return the max
                // value.
                newLowerBound = CodeUtil.maxValue(bits);
            }
        }
        if (newLowerBound < lowerBound) {
            // There is no lower bound which is greater than or equal to the current bound
            // so return the max value.
            return CodeUtil.maxValue(bits);
        }
        return newLowerBound;
    }

public static IntegerStamp stampForMask(int bits, long mustBeSet, long mayBeSet) {
        /*
         * Determine if the new stamp created by down & mayBeSet would be contradicting, i.e., empty
         * by definition. This can happen for example if binary logic operations are evaluated
         * repetitively on different branches creating values that are infeasible by definition
         * (logic nodes on phi nodes of false evaluated predecessors).
         */
        if ((mustBeSet & ~mayBeSet) != 0L) {
            return createEmptyStamp(bits);
        }
        return new IntegerStamp(bits, minValueForMasks(bits, mustBeSet, mayBeSet), maxValueForMasks(bits, mustBeSet, mayBeSet), mustBeSet, mayBeSet, true);
    }

public boolean hasValues() {
        return lowerBound <= upperBound;
    }

public long lowerBound() {
        return lowerBound;
    }

public long upperBound() {
        return upperBound;
    }

public long mustBeSet() {
        return mustBeSet;
    }

public long mayBeSet() {
        return mayBeSet;
    }

public boolean isUnrestricted() {
        return lowerBound == CodeUtil.minValue(getBits()) && upperBound == CodeUtil.maxValue(getBits()) && mustBeSet == 0 && mayBeSet == CodeUtil.mask(getBits()) && canBeZero;
    }

public boolean contains(long value) {
        return contains(value, canBeZero);
    }

private boolean contains(long value, boolean isCanBeZero) {
        if (value == 0 && !isCanBeZero) {
            /*
             * Special case partially canonicalized graphs and constants: If a guarded pi was
             * created with canBeZero=false but we feed in a constant 0
             */
            if (lowerBound == upperBound && lowerBound == 0) {
                return true;
            }
            return false;
        }
        return value >= lowerBound && value <= upperBound && (value & mustBeSet) == mustBeSet && (value & mayBeSet) == (value & CodeUtil.mask(getBits()));
    }

public static boolean addOverflowsPositively(long x, long y, int bits) {
        long result = x + y;
        if (bits == 64) {
            return (~x & ~y & result) < 0;
        } else {
            return result > CodeUtil.maxValue(bits);
        }
    }

public static boolean addOverflowsNegatively(long x, long y, int bits) {
        long result = x + y;
        if (bits == 64) {
            return (x & y & ~result) < 0;
        } else {
            return result < CodeUtil.minValue(bits);
        }
    }

public static long carryBits(long x, long y) {
        return (x + y) ^ x ^ y;
    }

static Stamp foldNeg(Stamp s) {
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

static Stamp foldAdd(Stamp stamp1, Stamp stamp2) {
                            if (stamp1.isEmpty()) {
                                return stamp1;
                            }
                            if (stamp2.isEmpty()) {
                                return stamp2;
                            }
                            IntegerStamp a = (IntegerStamp) stamp1;
                            IntegerStamp b = (IntegerStamp) stamp2;

                            int bits = a.getBits();
                            assert bits == b.getBits() : String.format("stamp1.bits=%d, stamp2.bits=%d", bits, b.getBits());

                            if (a.lowerBound == a.upperBound && b.lowerBound == b.upperBound) {
                                long value = CodeUtil.convert(a.lowerBound() + b.lowerBound(), a.getBits(), false);
                                return createConstant(a.getBits(), value);
                            }

                            if (a.isUnrestricted()) {
                                return a;
                            } else if (b.isUnrestricted()) {
                                return b;
                            }
                            long defaultMask = CodeUtil.mask(bits);
                            long variableBits = (a.mustBeSet() ^ a.mayBeSet()) | (b.mustBeSet() ^ b.mayBeSet());
                            long variableBitsWithCarry = variableBits | (carryBits(a.mustBeSet(), b.mustBeSet()) ^ carryBits(a.mayBeSet(), b.mayBeSet()));
                            long newMustBeSet = (a.mustBeSet() + b.mustBeSet()) & ~variableBitsWithCarry;
                            long newMayBeSet = (a.mustBeSet() + b.mustBeSet()) | variableBitsWithCarry;

                            newMustBeSet &= defaultMask;
                            newMayBeSet &= defaultMask;

                            long newLowerBound;
                            long newUpperBound;
                            boolean lowerOverflowsPositively = addOverflowsPositively(a.lowerBound(), b.lowerBound(), bits);
                            boolean upperOverflowsPositively = addOverflowsPositively(a.upperBound(), b.upperBound(), bits);
                            boolean lowerOverflowsNegatively = addOverflowsNegatively(a.lowerBound(), b.lowerBound(), bits);
                            boolean upperOverflowsNegatively = addOverflowsNegatively(a.upperBound(), b.upperBound(), bits);
                            if ((lowerOverflowsNegatively && !upperOverflowsNegatively) || (!lowerOverflowsPositively && upperOverflowsPositively)) {
                                newLowerBound = CodeUtil.minValue(bits);
                                newUpperBound = CodeUtil.maxValue(bits);
                            } else {
                                newLowerBound = CodeUtil.signExtend((a.lowerBound() + b.lowerBound()) & defaultMask, bits);
                                newUpperBound = CodeUtil.signExtend((a.upperBound() + b.upperBound()) & defaultMask, bits);
                            }
                            IntegerStamp limit = create(bits, newLowerBound, newUpperBound);
                            newMayBeSet &= limit.mayBeSet();
                            newUpperBound = CodeUtil.signExtend(newUpperBound & newMayBeSet, bits);
                            newMustBeSet |= limit.mustBeSet();
                            newLowerBound |= newMustBeSet;
                            return IntegerStamp.create(bits, newLowerBound, newUpperBound, newMustBeSet, newMayBeSet);
                        }

static Stamp foldSub(Stamp a, Stamp b) {
                            return OPS.getAdd().foldStamp(a, OPS.getNeg().foldStamp(b));
                        }

static Stamp foldNot(Stamp stamp) {
                            if (stamp.isEmpty()) {
                                return stamp;
                            }
                            IntegerStamp integerStamp = (IntegerStamp) stamp;
                            int bits = integerStamp.getBits();
                            long defaultMask = CodeUtil.mask(bits);
                            long lowerBoundInput = ~integerStamp.upperBound();
                            long upperBoundInput = ~integerStamp.lowerBound();
                            long mustBeSet1 = (~integerStamp.mayBeSet()) & defaultMask;
                            long mayBeSet1 = (~integerStamp.mustBeSet()) & defaultMask;
                            return IntegerStamp.create(bits, lowerBoundInput, upperBoundInput, mustBeSet1, mayBeSet1);
                        }

static Stamp foldAnd(Stamp stamp1, Stamp stamp2) {
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

static Stamp foldOr(Stamp stamp1, Stamp stamp2) {
                            if (stamp1.isEmpty()) {
                                return stamp1;
                            }
                            if (stamp2.isEmpty()) {
                                return stamp2;
                            }
                            IntegerStamp a = (IntegerStamp) stamp1;
                            IntegerStamp b = (IntegerStamp) stamp2;
                            assert a.getBits() == b.getBits() : "Bits must match " + Assertions.errorMessageContext("a", a, "b", b);

                            return stampForMask(a.getBits(), a.mustBeSet() | b.mustBeSet(), a.mayBeSet() | b.mayBeSet());
                        }

static Stamp foldXor(Stamp stamp1, Stamp stamp2) {
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

  static IntegerStamp call(String op,IntegerStamp a,IntegerStamp b){
    return (IntegerStamp)switch(op){case "and"->foldAnd(a,b);case "or"->foldOr(a,b);
      case "xor"->foldXor(a,b);case "add"->foldAdd(a,b);case "sub"->foldSub(a,b);
      default->throw new IllegalArgumentException(op);};
  }
  public static void main(String[] args) throws Exception {
    BufferedReader in=new BufferedReader(new InputStreamReader(System.in));
    BufferedWriter out=new BufferedWriter(new OutputStreamWriter(System.out));String line;
    while((line=in.readLine())!=null){
      try {
        String[] a=line.split(" ");int bits=Integer.parseInt(a[1]);long mask=CodeUtil.mask(bits);IntegerStamp r;
        if(a[0].equals("upper")) {
          long result=computeUpperBound(bits,Long.parseLong(a[2]),Long.parseUnsignedLong(a[3],16),Long.parseUnsignedLong(a[4],16),a[5].equals("1"));
          out.write("UP "+result+"\n");continue;
        }
        if(a[0].equals("lower")) {
          long result=computeLowerBound(bits,Long.parseLong(a[2]),Long.parseUnsignedLong(a[3],16),Long.parseUnsignedLong(a[4],16),a[5].equals("1"));
          out.write("LO "+result+"\n");continue;
        }
        if(a[0].equals("create")) {
          r=create(bits,Long.parseLong(a[2]),Long.parseLong(a[3]),Long.parseUnsignedLong(a[4],16),Long.parseUnsignedLong(a[5],16),a[6].equals("1"));
        } else {
          long za=Long.parseUnsignedLong(a[2],16),oa=Long.parseUnsignedLong(a[3],16),zb=Long.parseUnsignedLong(a[4],16),ob=Long.parseUnsignedLong(a[5],16);
          if((za&oa)!=0 || (zb&ob)!=0 || ((za|oa|zb|ob)&~mask)!=0)throw new IllegalArgumentException("input contract");
          IntegerStamp x=stampForMask(bits,oa,(~za)&mask),y=stampForMask(bits,ob,(~zb)&mask);
          r=call(a[0],x,y);
        }
        out.write("OK "+r.lowerBound+" "+r.upperBound+" "+Long.toUnsignedString(r.mustBeSet,16)+" "+Long.toUnsignedString(r.mayBeSet,16)+" "+(r.canBeZero?1:0)+"\n");
      } catch(Throwable e){out.write("ERROR "+e.getClass().getSimpleName()+" "+e.getMessage()+"\n");}
    }
    out.flush();
  }
}
